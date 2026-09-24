/** Each pipeline step as a person reads it on the build's checklist; a step missing here shows its own name. */
const STEP_NAMES: Readonly<Record<string, string>> = {
    labels: "Importing your labels",
    modules: "Reading your modules",
    "sample-files": "Reading your sample folders",
    notes: "Reading module notes",
    thumbnails: "Drawing waveforms",
    equivalence: "Finding near-duplicates",
    relink: "Matching your labels to samples",
    teacher: "Analyzing samples",
    "hearing-teacher": "Analyzing samples at their played pitch",
    categories: "Suggesting categories",
    "grid-cache": "Preparing spectrograms",
    descriptor: "Preparing the descriptor",
    embedding: "Describing samples",
    completion: "Describing new samples",
    evaluation: "Checking descriptor quality",
    "module-evaluation": "Checking descriptor quality on modules",
    cloud: "Building the cloud",
    "module-cloud": "Building the module cloud",
};

export function stepName(step: string): string {
    return STEP_NAMES[step] ?? step;
}
