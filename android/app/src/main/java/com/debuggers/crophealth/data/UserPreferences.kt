package com.debuggers.crophealth.data

import android.content.Context
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import com.debuggers.crophealth.domain.AppLanguage
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import java.io.IOException

private val Context.cropPreferences by preferencesDataStore("crop-preferences")
data class PreferenceState(val language: AppLanguage, val autoAudio: Boolean, val welcomed: Boolean)

class UserPreferences(context: Context) {
    private val store = context.applicationContext.cropPreferences
    private val languageKey = stringPreferencesKey("language")
    private val audioKey = booleanPreferencesKey("auto-audio")
    private val welcomeKey = booleanPreferencesKey("welcome-complete")
    val state = store.data.catch { failure ->
        if (failure is IOException) emit(emptyPreferences()) else throw failure
    }.map { PreferenceState(AppLanguage.fromId(it[languageKey] ?: "en"), it[audioKey] ?: false, it[welcomeKey] ?: false) }
    suspend fun language(value: AppLanguage) { store.edit { it[languageKey] = value.id } }
    suspend fun audio(value: Boolean) { store.edit { it[audioKey] = value } }
    suspend fun welcomed() { store.edit { it[welcomeKey] = true } }
}
