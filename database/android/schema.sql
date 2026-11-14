-- Room database version 1: copied from generated CropDatabase_Impl.createAllTables.
-- Source entity: android/app/src/main/java/com/debuggers/crophealth/data/ObservationStore.kt
-- This documents the real local Android database; it is not a backend service.

CREATE TABLE IF NOT EXISTS `observations` (`id` TEXT NOT NULL, `createdAt` INTEGER NOT NULL, `cropId` TEXT NOT NULL, `imagePath` TEXT, `resultType` TEXT NOT NULL, `conditionId` TEXT, `score` REAL, `modelVersion` TEXT NOT NULL, `inferenceMs` INTEGER NOT NULL, `note` TEXT NOT NULL, `validated` INTEGER NOT NULL, PRIMARY KEY(`id`));

CREATE TABLE IF NOT EXISTS room_master_table (id INTEGER PRIMARY KEY,identity_hash TEXT);

INSERT OR REPLACE INTO room_master_table (id,identity_hash) VALUES(42, 'bd9186869340845a31e9f93768d80efa');
