package com.debuggers.crophealth.domain

data class ConditionLabel(
    val index: Int,
    val id: String,
    val crop: Crop,
    val sourceLabel: String,
    val nameEn: String,
    val nameKn: String,
    val isHealthy: Boolean = false,
    val isPest: Boolean = false,
    val nameHi: String = nameEn,
) {
    fun displayName(language: AppLanguage): String = when (language) {
        AppLanguage.ENGLISH -> nameEn
        AppLanguage.KANNADA -> nameKn
        AppLanguage.HINDI -> nameHi
    }
}

/** Stable ordering shared with contracts/labels.json. Names are prototype translations. */
object Conditions {
    val all: List<ConditionLabel> = listOf(
        ConditionLabel(0, "maize_gray_leaf_spot", Crop.MAIZE, "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot", "Gray leaf spot", "ಬೂದು ಎಲೆ ಚುಕ್ಕೆ", nameHi = "धूसर पत्ती धब्बा"),
        ConditionLabel(1, "maize_common_rust", Crop.MAIZE, "Corn_(maize)___Common_rust_", "Common rust", "ಸಾಮಾನ್ಯ ತುಕ್ಕು ರೋಗ", nameHi = "सामान्य रतुआ"),
        ConditionLabel(2, "maize_northern_leaf_blight", Crop.MAIZE, "Corn_(maize)___Northern_Leaf_Blight", "Northern leaf blight", "ಉತ್ತರ ಎಲೆ ಅಂಗಮಾರಿ", nameHi = "उत्तरी पत्ती झुलसा"),
        ConditionLabel(3, "maize_healthy", Crop.MAIZE, "Corn_(maize)___healthy", "Healthy-looking leaf", "ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಎಲೆ", isHealthy = true, nameHi = "स्वस्थ दिखती पत्ती"),
        ConditionLabel(4, "potato_early_blight", Crop.POTATO, "Potato___Early_blight", "Early blight", "ಆರಂಭಿಕ ಅಂಗಮಾರಿ", nameHi = "अगेती झुलसा"),
        ConditionLabel(5, "potato_late_blight", Crop.POTATO, "Potato___Late_blight", "Late blight", "ತಡವಾದ ಅಂಗಮಾರಿ", nameHi = "पछेती झुलसा"),
        ConditionLabel(6, "potato_healthy", Crop.POTATO, "Potato___healthy", "Healthy-looking leaf", "ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಎಲೆ", isHealthy = true, nameHi = "स्वस्थ दिखती पत्ती"),
        ConditionLabel(7, "tomato_bacterial_spot", Crop.TOMATO, "Tomato___Bacterial_spot", "Bacterial spot", "ಬ್ಯಾಕ್ಟೀರಿಯಾ ಎಲೆ ಚುಕ್ಕೆ", nameHi = "जीवाणु पत्ती धब्बा"),
        ConditionLabel(8, "tomato_early_blight", Crop.TOMATO, "Tomato___Early_blight", "Early blight", "ಆರಂಭಿಕ ಅಂಗಮಾರಿ", nameHi = "अगेती झुलसा"),
        ConditionLabel(9, "tomato_late_blight", Crop.TOMATO, "Tomato___Late_blight", "Late blight", "ತಡವಾದ ಅಂಗಮಾರಿ", nameHi = "पछेती झुलसा"),
        ConditionLabel(10, "tomato_leaf_mold", Crop.TOMATO, "Tomato___Leaf_Mold", "Leaf mold", "ಎಲೆಯ ಶಿಲೀಂಧ್ರ ಕಲೆ", nameHi = "पत्ती की फफूंद"),
        ConditionLabel(11, "tomato_septoria_leaf_spot", Crop.TOMATO, "Tomato___Septoria_leaf_spot", "Septoria leaf spot", "ಸೆಪ್ಟೋರಿಯಾ ಎಲೆ ಚುಕ್ಕೆ", nameHi = "सेप्टोरिया पत्ती धब्बा"),
        ConditionLabel(12, "tomato_spider_mites", Crop.TOMATO, "Tomato___Spider_mites Two-spotted_spider_mite", "Two-spotted spider mites", "ಎರಡು ಚುಕ್ಕೆ ಜೇಡನುಸಿ", isPest = true, nameHi = "दो धब्बों वाला मकड़ी घुन"),
        ConditionLabel(13, "tomato_target_spot", Crop.TOMATO, "Tomato___Target_Spot", "Target spot", "ಗುರಿ ಆಕಾರದ ಎಲೆ ಚುಕ್ಕೆ", nameHi = "लक्ष्याकार धब्बा"),
        ConditionLabel(14, "tomato_yellow_leaf_curl_virus", Crop.TOMATO, "Tomato___Tomato_Yellow_Leaf_Curl_Virus", "Yellow leaf curl virus", "ಹಳದಿ ಎಲೆ ಸುರುಳಿ ವೈರಸ್", nameHi = "पीली पत्ती मुड़ने का वायरस"),
        ConditionLabel(15, "tomato_mosaic_virus", Crop.TOMATO, "Tomato___Tomato_mosaic_virus", "Mosaic virus", "ಮೊಸಾಯಿಕ್ ವೈರಸ್", nameHi = "मोज़ेक वायरस"),
        ConditionLabel(16, "tomato_healthy", Crop.TOMATO, "Tomato___healthy", "Healthy-looking leaf", "ಆರೋಗ್ಯಕರವಾಗಿ ಕಾಣುವ ಎಲೆ", isHealthy = true, nameHi = "स्वस्थ दिखती पत्ती"),
    )
    val ids: Set<String> = all.map { it.id }.toSet()
    fun byId(id: String): ConditionLabel? = all.firstOrNull { it.id == id }
    fun forCrop(crop: Crop): List<ConditionLabel> = all.filter { it.crop == crop }
}
