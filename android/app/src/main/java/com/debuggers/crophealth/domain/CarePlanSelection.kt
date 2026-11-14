package com.debuggers.crophealth.domain

import com.debuggers.crophealth.content.CareStagePlan

/** Missing severity must never silently select mild treatment priorities. */
object CarePlanSelection {
    fun stage(plans: Map<String, CareStagePlan>, severity: ReportedSeverity): CareStagePlan? = when (severity) {
        ReportedSeverity.MILD -> plans["MILD"]
        ReportedSeverity.MODERATE -> plans["MODERATE"]
        ReportedSeverity.SEVERE -> plans["SEVERE"]
        ReportedSeverity.UNKNOWN, ReportedSeverity.NONE -> null
    }
}
