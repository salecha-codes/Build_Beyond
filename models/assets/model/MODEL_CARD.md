# MobileNetV4-Conv-Small prototype

Training status: **trained_prototype**.

This bundle contains a real executable V4 model, but is **not validated for disease diagnosis**. The decision policy deliberately keeps predictions uncertain. Export parity is a pipeline check, not evidence of recognition quality. No phone latency or RAM result is claimed.

Classes: 17; pooled embedding dimension: 960; preprocessing and hashes are in model_metadata.json. Raw scores must not be presented as validated probabilities or pesticide instructions.

See training/export receipts for exact executed work.

## Executed training evidence

The selected epoch14 checkpoint follows15 total source-domain scratch-training epochs (3 initial +12 continued). It used2,152 training images and536 model-selection validation images. Selected validation accuracy:60.45%; macroF1:0.5902. These are not independent test or field results. The longer candidate was not selected using a repeated final-test inspection.

Temperature was fitted on actual exported-model source-validation logits: 0.8857924395488052. Validation NLL changed from 1.1451541166639705 to 1.1378339698126594. This is not independent field calibration; acceptance thresholds and the diagnosis gate remain unvalidated. All536 exported validation logits were compared with the selected checkpoint outputs.
