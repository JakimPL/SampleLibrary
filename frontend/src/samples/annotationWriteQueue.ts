import {
    type AnnotationChanges,
    type AnnotationScope,
    type AnnotationsWritten,
    changeSampleAnnotation,
} from "../api/curation";
import { describeError } from "../shared/fetchState";
import { useAnnotationStore } from "./annotationStore";

const tailBySampleHash = new Map<string, Promise<void>>();
const groupBySampleHash = new Map<string, readonly string[]>();
let lastSequence = 0;

/** The samples a change is known to reach before it is sent: the sample alone, or the group learned from earlier answers. */
function knownReach(sampleHash: string, scope: AnnotationScope): readonly string[] {
    return scope === "equivalence_class" ? (groupBySampleHash.get(sampleHash) ?? [sampleHash]) : [sampleHash];
}

function learnGroup(written: AnnotationsWritten): void {
    const members = [...written.samples.map((item) => item.sample_hash), ...written.skipped];
    for (const member of members) {
        groupBySampleHash.set(member, members);
    }
}

/**
 * Send one change, after every change already on its way to any sample it reaches.
 *
 * Two gestures made quickly on one sample -- a label typed, then a star clicked -- reach the server in
 * the order they were made, and each answer lands in the session store in that order too. Changes to
 * unrelated samples go out side by side. A change shows in the store as soon as it is queued, so the
 * screen follows the gesture rather than the round trip.
 */
export function queueAnnotationChange(
    sampleHash: string,
    scope: AnnotationScope,
    changes: AnnotationChanges,
): Promise<AnnotationsWritten> {
    lastSequence += 1;
    const sequence = lastSequence;
    const reach = knownReach(sampleHash, scope);
    const store = useAnnotationStore.getState();
    store.beginChange(sequence, reach, changes);

    const earlier = Promise.allSettled(reach.map((member) => tailBySampleHash.get(member) ?? Promise.resolve()));
    const answered = earlier
        .then(() => changeSampleAnnotation(sampleHash, scope, changes))
        .then(
            (written) => {
                if (scope === "equivalence_class") {
                    learnGroup(written);
                }
                useAnnotationStore.getState().settleChange(sequence, reach, written);
                return written;
            },
            (error: unknown) => {
                useAnnotationStore.getState().failChange(sequence, reach, describeError(error));
                throw error;
            },
        );

    const tail = answered.then(
        () => undefined,
        () => undefined,
    );
    for (const member of reach) {
        tailBySampleHash.set(member, tail);
    }
    void tail.then(() => {
        for (const member of reach) {
            if (tailBySampleHash.get(member) === tail) {
                tailBySampleHash.delete(member);
            }
        }
    });
    return answered;
}

/** Forgets every queued change and learned group. Exists for tests, where each case starts clean. */
export function resetAnnotationWriteQueue(): void {
    tailBySampleHash.clear();
    groupBySampleHash.clear();
    lastSequence = 0;
}
