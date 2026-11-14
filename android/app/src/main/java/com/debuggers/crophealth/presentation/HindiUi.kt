package com.debuggers.crophealth.presentation

import android.content.Context
import org.json.JSONObject

/** Bundled UI translations only: no network or Android language-pack dependency. */
object HindiUi {
    @Volatile private var translations: Map<String, String> = emptyMap()
    @Volatile private var loaded = false

    @Synchronized
    fun load(context: Context) {
        if (loaded) return
        runCatching {
            val root = context.assets.open("content/hindi_ui.json").bufferedReader().use { JSONObject(it.readText()) }
            val values = root.optJSONObject("translations") ?: root
            translations = values.keys().asSequence().mapNotNull { key ->
                (values.opt(key) as? String)?.takeIf { it.isNotBlank() }?.let { key to it }
            }.toMap()
            loaded = true
        }
    }

    fun translate(english: String): String {
        translations[english]?.let { return it }
        return when {
            english.startsWith("Local model unavailable:") -> translations["Local model unavailable"] ?: "स्थानीय मॉडल उपलब्ध नहीं है"
            english.startsWith("Listen in ") -> "हिन्दी में सुनें"
            english.startsWith("Version: ") -> "संस्करण: " + english.removePrefix("Version: ")
            english.matches(Regex("Question [1-3] of 3")) -> "प्रश्न ${english.removePrefix("Question ").substringBefore(" of ")} / 3"
            else -> english
        }
    }
}
