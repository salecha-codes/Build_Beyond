package com.debuggers.crophealth.domain

/** Old uncertainty was stored globally: a false Boolean cannot be inferred as No. */
object CareAnswerDraft {
    fun seed(symptoms: ReportedSymptoms, completed: Boolean): List<Int> {
        if (!completed) return List(6) { -1 }
        fun yesNo(value: Boolean) = if (value) 0 else if (symptoms.uncertainAnswers) -1 else 1
        return listOf(yesNo(symptoms.spreadingQuickly), when (symptoms.leafCoverage) {
            LeafCoverage.NO_VISIBLE_DAMAGE -> 0
            LeafCoverage.FEW_SPOTS -> 1
            LeafCoverage.SOME_SPOTS -> 2
            LeafCoverage.MANY_SPOTS -> 3
            LeafCoverage.NOT_REPORTED -> 4
        }, yesNo(symptoms.manyPlantsAffected), yesNo(symptoms.wiltingOrDying),
            yesNo(symptoms.fruitOrStemAffected), yesNo(symptoms.wetWeather))
    }

    fun symptoms(answers: List<Int>): ReportedSymptoms {
        require(answers.size == 6)
        return ReportedSymptoms(
            spreadingQuickly = answers[0] == 0,
            manyPlantsAffected = answers[2] == 0,
            wiltingOrDying = answers[3] == 0,
            leafCoverage = when (answers[1]) {
                0 -> LeafCoverage.NO_VISIBLE_DAMAGE; 1 -> LeafCoverage.FEW_SPOTS
                2 -> LeafCoverage.SOME_SPOTS; 3 -> LeafCoverage.MANY_SPOTS
                else -> LeafCoverage.NOT_REPORTED
            },
            uncertainAnswers = answers.withIndex().any { (index, answer) -> answer < 0 || answer == if (index == 1) 4 else 2 },
            fruitOrStemAffected = answers[4] == 0,
            wetWeather = answers[5] == 0,
        )
    }
}
