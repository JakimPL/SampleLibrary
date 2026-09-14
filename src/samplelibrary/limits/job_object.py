from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any, Final

from samplelibrary.limits.ceiling import MemoryCeiling
from samplelibrary.limits.scope import MemoryScopeUnavailable

# The Windows job object flags and information class this boundary uses, from winnt.h: a job may
# hold every process inside it to one committed-memory total, and closing the last handle to the job
# ends everything still running in it.
JOB_OBJECT_LIMIT_JOB_MEMORY: Final[int] = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: Final[int] = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: Final[int] = 9
JOB_OBJECT_QUERY: Final[int] = 0x0004
JOB_NAME_PREFIX: Final[str] = "Local\\"


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    # pylint: disable=invalid-name,attribute-defined-outside-init
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JobObjectScope:  # pylint: disable=invalid-name,attribute-defined-outside-init,unused-argument
    """A memory ceiling held by a Windows job object this process assigns itself to.

    Every process started afterwards joins the job, so a command and its workers hold the ceiling
    between them. Windows counts committed memory rather than resident memory, which is the stricter
    reading of the same number, and an allocation past the ceiling fails where another system's
    kernel would stop the process. The handle stays open for the life of the process, so the job
    ends with it and takes any process still running in it along.
    """

    def __init__(self) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        self._held: list[int] = []

    def enter(self, name: str, ceiling: MemoryCeiling, restart: list[str]) -> None:
        """Assign this process to a job of this name holding the ceiling.

        Raises:
            MemoryScopeUnavailable: Windows refused the job, its limit, or the assignment.
        """
        if ceiling.byte_count is None:
            return
        job = self._kernel32.CreateJobObjectW(None, _job_name(name))
        if not job:
            raise MemoryScopeUnavailable(f"Windows refused a job object for {name} ({_last_error()})")
        information = _ExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        information.JobMemoryLimit = ceiling.byte_count
        if not self._kernel32.SetInformationJobObject(
            job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(information), ctypes.sizeof(information)
        ):
            raise MemoryScopeUnavailable(f"Windows refused the memory limit for {name} ({_last_error()})")
        if not self._kernel32.AssignProcessToJobObject(job, self._kernel32.GetCurrentProcess()):
            raise MemoryScopeUnavailable(f"Windows refused to put this process in {name} ({_last_error()})")
        self._held.append(job)

    def is_running(self, name: str) -> bool:
        """Whether a job of this name is still open, which is what an orphaned step leaves behind."""
        job = self._kernel32.OpenJobObjectW(JOB_OBJECT_QUERY, False, _job_name(name))
        if not job:
            return False
        self._kernel32.CloseHandle(job)
        return True

    def terminate(self, name: str) -> None:
        """End every process in the job of this name, which is how a whole step's tree goes at once."""
        job = self._kernel32.OpenJobObjectW(JOB_OBJECT_QUERY | 0x0008, False, _job_name(name))
        if not job:
            return
        self._kernel32.TerminateJobObject(job, 1)
        self._kernel32.CloseHandle(job)

    def peak_bytes(self) -> int | None:
        """The most committed memory the job ever held at once, as Windows recorded it."""
        if not self._held:
            return None
        information = _ExtendedLimitInformation()
        returned = wintypes.DWORD(0)
        if not self._kernel32.QueryInformationJobObject(
            self._held[-1],
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
            ctypes.byref(returned),
        ):
            return None
        return int(information.PeakJobMemoryUsed)

    def reached_the_ceiling(self) -> bool:
        """Whether the job ever held as much memory as its ceiling allows, which is where allocations start failing."""
        peak = self.peak_bytes()
        limit = self._limit()
        return peak is not None and limit is not None and peak >= limit

    def _limit(self) -> int | None:
        if not self._held:
            return None
        information = _ExtendedLimitInformation()
        returned = wintypes.DWORD(0)
        if not self._kernel32.QueryInformationJobObject(
            self._held[-1],
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
            ctypes.byref(returned),
        ):
            return None
        return int(information.JobMemoryLimit)


def _last_error() -> int:
    """The code Windows last set for this thread.

    The typeshed stubs declare this call on Windows alone, which is the only platform this module
    loads on, so the reference is read here once rather than at every refusal.
    """
    return int(ctypes.get_last_error())  # type: ignore[attr-defined]


def _job_name(name: str) -> Any:
    """A job's name in the session's own namespace, which is where another process of this user finds it."""
    return ctypes.c_wchar_p(f"{JOB_NAME_PREFIX}{name}")
