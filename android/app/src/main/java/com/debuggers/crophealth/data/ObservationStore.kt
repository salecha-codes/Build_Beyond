package com.debuggers.crophealth.data

import android.content.Context
import androidx.room.*
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.debuggers.crophealth.domain.Crop
import com.debuggers.crophealth.domain.LeafCoverage
import com.debuggers.crophealth.domain.ReportedSymptoms
import com.debuggers.crophealth.presentation.Observation
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.io.File
import org.json.JSONObject

@Entity(tableName = "observations")
data class ObservationEntity(
    @PrimaryKey val id: String,
    val createdAt: Long,
    val cropId: String,
    val imagePath: String?,
    val resultType: String,
    val conditionId: String?,
    val score: Float?,
    val modelVersion: String,
    val inferenceMs: Long,
    val note: String,
    val validated: Boolean,
    val reportedSymptomsJson: String? = null,
) {
    fun observation() = Observation(id, createdAt, Crop.fromId(cropId) ?: Crop.TOMATO, imagePath,
        resultType, conditionId, score, modelVersion, inferenceMs, note, validated, ReportedSymptomsJson.decode(reportedSymptomsJson))

    companion object {
        fun from(value: Observation) = with(value) {
            ObservationEntity(id, createdAt, crop.id, imagePath, resultType, conditionId, score, modelVersion, inferenceMs, note, validated,
                reportedSymptoms?.let(ReportedSymptomsJson::encode))
        }
    }
}

@Dao interface ObservationDao {
    @Query("SELECT * FROM observations ORDER BY createdAt DESC") fun observe(): Flow<List<ObservationEntity>>
    @Query("SELECT * FROM observations WHERE id = :id") suspend fun find(id: String): ObservationEntity?
    @Query("SELECT * FROM observations") suspend fun all(): List<ObservationEntity>
    @Query("SELECT COUNT(*) FROM observations WHERE imagePath = :path") suspend fun references(path: String): Int
    @Insert(onConflict = OnConflictStrategy.ABORT) suspend fun insert(value: ObservationEntity)
    @Query("UPDATE observations SET reportedSymptomsJson = :json WHERE id = :id") suspend fun updateSymptoms(id: String, json: String)
    @Query("DELETE FROM observations WHERE id = :id") suspend fun delete(id: String)
    @Query("DELETE FROM observations") suspend fun clear()
}

@Database(entities = [ObservationEntity::class], version = 2, exportSchema = false)
abstract class CropDatabase : RoomDatabase() { abstract fun observations(): ObservationDao }

val OBSERVATION_MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE observations ADD COLUMN reportedSymptomsJson TEXT")
    }
}

object ReportedSymptomsJson {
    fun encode(value: ReportedSymptoms): String = JSONObject().apply {
        put("spreadingQuickly", value.spreadingQuickly); put("manyPlantsAffected", value.manyPlantsAffected)
        put("wiltingOrDying", value.wiltingOrDying); put("leafCoverage", value.leafCoverage.name)
        put("uncertainAnswers", value.uncertainAnswers); put("fruitOrStemAffected", value.fruitOrStemAffected)
        put("wetWeather", value.wetWeather)
    }.toString()
    fun decode(value: String?): ReportedSymptoms? = value?.let { runCatching {
        val item = JSONObject(it)
        ReportedSymptoms(item.optBoolean("spreadingQuickly"), item.optBoolean("manyPlantsAffected"),
            item.optBoolean("wiltingOrDying"), runCatching { LeafCoverage.valueOf(item.optString("leafCoverage")) }.getOrDefault(LeafCoverage.NOT_REPORTED),
            item.optBoolean("uncertainAnswers"), item.optBoolean("fruitOrStemAffected"), item.optBoolean("wetWeather"))
    }.getOrNull() }
}

class ObservationStore(context: Context) : AutoCloseable {
    private val owner = context.applicationContext
    private val directory = File(owner.filesDir, "observations").apply { mkdirs() }
    private val database = Room.databaseBuilder(owner, CropDatabase::class.java, "crop-observations.db")
        .addMigrations(OBSERVATION_MIGRATION_1_2).build()
    private val dao = database.observations()
    val observations = dao.observe().map { values -> values.map(ObservationEntity::observation) }

    suspend fun save(value: Observation) = dao.insert(ObservationEntity.from(value))
    suspend fun find(id: String): Observation? = dao.find(id)?.observation()
    suspend fun updateSymptoms(id: String, symptoms: ReportedSymptoms) = dao.updateSymptoms(id, ReportedSymptomsJson.encode(symptoms))
    suspend fun delete(id: String) {
        val item = dao.find(id) ?: return
        dao.delete(id)
        item.imagePath?.let { if (dao.references(it) == 0) deleteOwnedImage(it) }
    }
    suspend fun clear() {
        val items = dao.all(); dao.clear()
        items.mapNotNull { it.imagePath }.distinct().forEach(::deleteOwnedImage)
    }
    private fun deleteOwnedImage(path: String) {
        val file = File(path)
        if (file.canonicalFile.parentFile == directory.canonicalFile) file.delete()
    }
    override fun close() = database.close()
}
