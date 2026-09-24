/** Each pipeline step as a person reads it on the build's checklist; a step missing here shows its own name. */
const STEP_NAMES: Readonly<Record<string, string>> = {
    labels: "Bringing in your labels",
    modules: "Reading your modules",
    "sample-files": "Reading your sample folders",
    notes: "Reading the notes each module plays",
    thumbnails: "Drawing waveforms",
    equivalence: "Finding near-duplicates",
    relink: "Reattaching your labels",
    teacher: "Listening to every sample",
    "hearing-teacher": "Listening at the pitch each sample is played",
    categories: "Suggesting categories",
    "grid-cache": "Preparing spectrograms",
    descriptor: "Training the descriptor",
    embedding: "Describing every sample",
    completion: "Describing the newest samples",
    evaluation: "Scoring the descriptor",
    "module-evaluation": "Scoring the descriptor on modules",
    cloud: "Laying out the cloud",
    "module-cloud": "Laying out the module cloud",
};

export function stepName(step: string): string {
    return STEP_NAMES[step] ?? step;
}
