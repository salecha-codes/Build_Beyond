# Review2 ML status

Selected Android candidate: `mnv4-conv-small-supervised_from_scratch-d157e7c84013`, SHA256 `d157e7c8401319a700039de467caba6728b7bdbf35b4cdae1818757cf0ba7e3c`. Real MobileNetV4-Conv-Small, 17 logits and960 pooled features.

All24,164 source RGB files were acquired, decoded and checked against pinned Git blob IDs. Fourteen exact copies were excluded from use. Known-group/exact-dedup partitions: train16,856 / validation3,620 / source test3,674. Source physical-leaf metadata is incomplete.

The bounded scratch run used2,152 train /536 validation images. Best selected checkpoint is epoch14 of15 total epochs: validation accuracy60.45%, macroF1 .5902. No final test is claimed for this longer candidate. Original3epoch held-out comparison is preserved separately in ../review2_3epoch and must not be attributed to this model.

Export checker/parity and actual CPU inference passed. Source-validation temperature fit improved NLL slightly. Policy AND metadata diagnosis validation remain false. No phone, field, pesticide-advice or calibrated acceptance claim is made. Pretrained HF downloads remained blocked.
