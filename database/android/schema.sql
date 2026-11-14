-- Room database version 2: copied from generated CropDatabase_Impl.createAllTables.
-- Source entity: android/app/src/main/java/com/debuggers/crophealth/data/ObservationStore.kt
-- This documents the real local Android database; it is not a backend service.

CREATE TABLE IF NOT EXISTS `observations` (`id` TEXT NOT NULL, `createdAt` INTEGER NOT NULL, `cropId` TEXT NOT NULL, `imagePath` TEXT, `resultType` TEXT NOT NULL, `conditionId` TEXT, `score` REAL, `modelVersion` TEXT NOT NULL, `inferenceMs` INTEGER NOT NULL, `note` TEXT NOT NULL, `validated` INTEGER NOT NULL, `reportedSymptomsJson` TEXT, PRIMARY KEY(`id`));

CREATE TABLE IF NOT EXISTS room_master_table (id INTEGER PRIMARY KEY,identity_hash TEXT);

INSERT OR REPLACE INTO room_master_table (id,identity_hash) VALUES(42, '35938378ce84fb66c7aa1e57f14d2a5a');

-- Upgrade 1 -> 2 (executed by OBSERVATION_MIGRATION_1_2; no history deletion):
-- ALTER TABLE observations ADD COLUMN reportedSymptomsJson TEXT;
-- NULL means no completed questionnaire; it is not interpreted as zero damage.
-- The JSON stores farmer answers only. Care/severity is recomputed by the current
-- versioned advisory decision model rather than permanently freezing an old grade.
