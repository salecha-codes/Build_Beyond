# Treatment and recovery model, version 2

The first advisory model changed the urgency badge but left care actions static.
Version 2 adds a separate conditional treatment knowledge model, stage selection
and a searchable offline care library. It covers the same 17 crop-condition IDs.

For each condition and supported language, the model stores:

- the management goal and observations needed to check the suspected cause;
- similar conditions that can need different management;
- treatment options with a use case, ordered steps, limitations and references;
- distinct mild, moderate and severe action pathways;
- actions to avoid, improvement signs and signs of treatment failure;
- follow-up checkpoints with an observation and a next action;
- questions that help a local adviser choose a registered intervention.

The app selects an actual action pathway from the farmer's reported severity.
Unknown severity does not select mild actions. A healthy-looking result with
reported symptoms leads to further evaluation rather than reassurance. Disease
scores do not determine severity, medicine dose or treatment efficacy.

The care library can be used before taking a photo. Its condition is explicitly
selected by the user, with a separate questionnaire session. Reading another
condition's protocol never relabels a saved photo or overwrites its inference.

`content/care_protocols.json` is the canonical knowledge artifact. Run
`python3 tools/build_care_protocols.py` to validate and package it. The receipt
records the data and implementation hashes. The old advisory knowledge and its
75 narration clips retain their original provenance. New treatment narration
has its own text/hash manifest, rather than pretending older recordings speak
the expanded treatment plan.

This is an authored knowledge-and-decision model. It has not been trained or
validated on treatment outcomes. More image-classification data cannot supply
missing efficacy or severity labels. Source access and dataset investigations
are documented in `docs/CARE_V2_RESEARCH.md`; a retrieved secondary dataset is
not presented as an independently verified primary recommendation. Named
chemical discussions require a retrieved source in packaging checks. Reference
materials do not establish local product registration, crop approval, dose,
harvest interval or resistance suitability. No such approval is inferred.

Recovery checkpoints are observations to reassess management, not promises of a
cure or pesticide application intervals. Existing dead leaf tissue does not
turn green after treatment. Virus profiles describe containment and protection
of other plants because there is no curative spray for the infected plant.

Engineering tests establish profile coverage, actual action selection, manual
session isolation, source linkage, offline behavior and playback integrity.
Agronomist review, native-language review and prospective field evaluation are
still required for agricultural validation.
