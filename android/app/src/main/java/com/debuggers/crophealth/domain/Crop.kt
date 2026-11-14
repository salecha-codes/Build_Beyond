package com.debuggers.crophealth.domain

enum class Crop(val id: String, val nameEn: String, val nameKn: String) {
    TOMATO("tomato", "Tomato", "ಟೊಮ್ಯಾಟೊ"),
    POTATO("potato", "Potato", "ಆಲೂಗಡ್ಡೆ"),
    MAIZE("maize", "Maize", "ಮೆಕ್ಕೆಜೋಳ");

    companion object {
        fun fromId(id: String): Crop? = entries.firstOrNull { it.id == id }
    }
}

enum class AppLanguage(val id: String, val displayName: String) {
    ENGLISH("en", "English"), KANNADA("kn", "ಕನ್ನಡ");
    companion object {
        fun fromId(id: String): AppLanguage = entries.firstOrNull { it.id == id } ?: ENGLISH
    }
}
