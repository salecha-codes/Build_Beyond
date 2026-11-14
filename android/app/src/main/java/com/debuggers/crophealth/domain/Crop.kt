package com.debuggers.crophealth.domain

enum class Crop(val id: String, val nameEn: String, val nameKn: String, val nameHi: String) {
    TOMATO("tomato", "Tomato", "ಟೊಮ್ಯಾಟೊ", "टमाटर"),
    POTATO("potato", "Potato", "ಆಲೂಗಡ್ಡೆ", "आलू"),
    MAIZE("maize", "Maize", "ಮೆಕ್ಕೆಜೋಳ", "मक्का");

    fun displayName(language: AppLanguage): String = when (language) {
        AppLanguage.ENGLISH -> nameEn
        AppLanguage.KANNADA -> nameKn
        AppLanguage.HINDI -> nameHi
    }

    companion object {
        fun fromId(id: String): Crop? = entries.firstOrNull { it.id == id }
    }
}

enum class AppLanguage(val id: String, val displayName: String) {
    ENGLISH("en", "English"), KANNADA("kn", "ಕನ್ನಡ"), HINDI("hi", "हिन्दी");

    fun next(): AppLanguage = entries[(ordinal + 1) % entries.size]

    companion object {
        fun fromId(id: String): AppLanguage = entries.firstOrNull { it.id == id } ?: ENGLISH
    }
}
