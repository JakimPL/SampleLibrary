import type { ReactElement } from "react";

interface OptionalLabelProps {
    readonly value: string;
    readonly placeholder: string;
}

export function OptionalLabel({ value, placeholder }: OptionalLabelProps): ReactElement {
    return value.trim() === "" ? <em>{placeholder}</em> : <>{value}</>;
}
