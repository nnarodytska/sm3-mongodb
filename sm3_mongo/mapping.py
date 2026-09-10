"""CSV row -> MQL document mappings.

Transcribed verbatim from SM3-Text-to-Query
``src/setup_dbs/mongodb/setup-mongodb.py`` (the ``map_*`` static methods).

Fidelity rules for this module:

* Field names are exactly what upstream writes, including the two that disagree
  with ``mql_schema`` in the prompt: ``PATIENT_DEPARTMENT_ID`` (prompt says
  ``PATIENTDEPARTMENT_ID``) and ``FEE_SCHEDULEID`` (prompt says
  ``FEE_SCHEDULE_ID``). Do not "correct" them: the database really has these.
* Casting is exactly upstream's. Unguarded ``int()`` / ``float()`` calls stay
  unguarded, so a malformed CSV raises here just as it does upstream.
* ``X if row[...] else None`` guards stay only where upstream has them, so an
  empty string becomes ``None`` in exactly the same fields.

Every function is pure: dict in, dict out, no I/O.
"""


def map_patients(row):
    return {
        "PATIENT_ID": row["Id"],
        "BIRTHDATE": row["BIRTHDATE"],
        "DEATHDATE": row["DEATHDATE"],
        "SSN": row["SSN"],
        "DRIVERS": row["DRIVERS"],
        "PASSPORT": row["PASSPORT"],
        "PREFIX": row["PREFIX"],
        "FIRST": row["FIRST"],
        "LAST": row["LAST"],
        "SUFFIX": row["SUFFIX"],
        "MAIDEN": row["MAIDEN"],
        "MARITAL": row["MARITAL"],
        "RACE": row["RACE"],
        "ETHNICITY": row["ETHNICITY"],
        "GENDER": row["GENDER"],
        "BIRTHPLACE": row["BIRTHPLACE"],
        "ADDRESS": row["ADDRESS"],
        "CITY": row["CITY"],
        "STATE": row["STATE"],
        "COUNTY": row["COUNTY"],
        "FIPS": float(row["FIPS"]) if row["FIPS"] else None,
        "ZIP": row["ZIP"],
        "LAT": float(row["LAT"]),
        "LON": float(row["LON"]),
        "HEALTHCARE_EXPENSES": float(row["HEALTHCARE_EXPENSES"]),
        "HEALTHCARE_COVERAGE": float(row["HEALTHCARE_COVERAGE"]),
        "INCOME": int(row["INCOME"]),
    }


def map_encounters(row):
    return {
        "ENCOUNTER_ID": row["Id"],
        "START": row["START"],
        "STOP": row["STOP"],
        "PATIENT_REF": row["PATIENT"],
        "ORGANIZATION_REF": row["ORGANIZATION"],
        "PROVIDER_REF": row["PROVIDER"],
        "PAYER_REF": row["PAYER"],
        "ENCOUNTER_CLASS": row["ENCOUNTERCLASS"],
        "CODE": int(row["CODE"]),
        "DESCRIPTION": row["DESCRIPTION"],
        "BASE_ENCOUNTER_COST": float(row["BASE_ENCOUNTER_COST"]),
        "TOTAL_CLAIM_COST": float(row["TOTAL_CLAIM_COST"]),
        "PAYER_COVERAGE": float(row["PAYER_COVERAGE"]),
        "REASON_CODE": int(row["REASONCODE"]) if row["REASONCODE"] else None,
        "REASON_DESCRIPTION": row["REASONDESCRIPTION"],
    }


def map_conditions(row):
    return {
        "START": row["START"],
        "STOP": row["STOP"],
        "PATIENT_REF": row["PATIENT"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "CODE": int(row["CODE"]),
        "DESCRIPTION": row["DESCRIPTION"],
    }


def map_allergies(row):
    return {
        "START": row["START"],
        "STOP": row["STOP"],
        "PATIENT_REF": row["PATIENT"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "CODE": int(row["CODE"]),
        "SYSTEM": row["SYSTEM"],
        "DESCRIPTION": row["DESCRIPTION"],
        "TYPE": row["TYPE"],
        "CATEGORY": row["CATEGORY"],
        "REACTION_1": int(row["REACTION1"]) if row["REACTION1"] else None,
        "DESCRIPTION_1": row["DESCRIPTION1"],
        "SEVERITY_1": row["SEVERITY1"],
        "REACTION_2": int(row["REACTION2"]) if row["REACTION2"] else None,
        "DESCRIPTION_2": row["DESCRIPTION2"],
        "SEVERITY_2": row["SEVERITY2"],
    }


def map_medications(row):
    return {
        "START": row["START"],
        "STOP": row["STOP"],
        "PATIENT_REF": row["PATIENT"],
        "PAYER_REF": row["PAYER"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "CODE": int(row["CODE"]),
        "DESCRIPTION": row["DESCRIPTION"],
        "BASE_COST": float(row["BASE_COST"]),
        "PAYER_COVERAGE": float(row["PAYER_COVERAGE"]),
        "DISPENSES": int(row["DISPENSES"]),
        "TOTAL_COST": float(row["TOTALCOST"]),
        "REASON_CODE": int(row["REASONCODE"]) if row["REASONCODE"] else None,
        "REASON_DESCRIPTION": row["REASONDESCRIPTION"],
    }


def map_careplans(row):
    return {
        "CAREPLAN_ID": row["Id"],
        "START": row["START"],
        "STOP": row["STOP"],
        "PATIENT_REF": row["PATIENT"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "CODE": int(row["CODE"]),
        "DESCRIPTION": row["DESCRIPTION"],
        "REASON_CODE": int(row["REASONCODE"]) if row["REASONCODE"] else None,
        "REASON_DESCRIPTION": row["REASONDESCRIPTION"],
    }


def map_observations(row):
    return {
        "DATE": row["DATE"],
        "PATIENT_REF": row["PATIENT"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "CATEGORY": row["CATEGORY"],
        "CODE": row["CODE"],
        "DESCRIPTION": row["DESCRIPTION"],
        "VALUE": row["VALUE"],
        "UNITS": row["UNITS"],
        "TYPE": row["TYPE"],
    }


def map_procedures(row):
    return {
        "START": row["START"],
        "STOP": row["STOP"],
        "PATIENT_REF": row["PATIENT"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "CODE": int(row["CODE"]),
        "DESCRIPTION": row["DESCRIPTION"],
        "BASE_COST": float(row["BASE_COST"]),
        "REASON_CODE": int(row["REASONCODE"]) if row["REASONCODE"] else None,
        "REASON_DESCRIPTION": row["REASONDESCRIPTION"],
    }


def map_immunizations(row):
    return {
        "DATE": row["DATE"],
        "PATIENT_REF": row["PATIENT"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "CODE": int(row["CODE"]),
        "DESCRIPTION": row["DESCRIPTION"],
        "BASE_COST": float(row["BASE_COST"]),
    }


def map_imaging_studies(row):
    return {
        "IMAGING_STUDY_ID": row["Id"],
        "DATE": row["DATE"],
        "PATIENT_REF": row["PATIENT"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "SERIES_UID": row["SERIES_UID"],
        "BODYSITE_CODE": int(row["BODYSITE_CODE"]),
        "BODYSITE_DESCRIPTION": row["BODYSITE_DESCRIPTION"],
        "MODALITY_CODE": row["MODALITY_CODE"],
        "MODALITY_DESCRIPTION": row["MODALITY_DESCRIPTION"],
        "INSTANCE_UID": row["INSTANCE_UID"],
        "SOP_CODE": row["SOP_CODE"],
        "SOP_DESCRIPTION": row["SOP_DESCRIPTION"],
        "PROCEDURE_CODE": int(row["PROCEDURE_CODE"]),
    }


def map_devices(row):
    return {
        "START": row["START"],
        "STOP": row["STOP"],
        "PATIENT_REF": row["PATIENT"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "CODE": int(row["CODE"]),
        "DESCRIPTION": row["DESCRIPTION"],
        "UDI": row["UDI"],
    }


def map_supplies(row):
    return {
        "DATE": row["DATE"],
        "PATIENT_REF": row["PATIENT"],
        "ENCOUNTER_REF": row["ENCOUNTER"],
        "CODE": int(row["CODE"]),
        "DESCRIPTION": row["DESCRIPTION"],
        "QUANTITY": int(row["QUANTITY"]),
    }


def map_claims(row):
    return {
        "CLAIM_ID": row["Id"],
        "PATIENT_REF": row["PATIENTID"],
        "PROVIDER_REF": row["PROVIDERID"],
        "PRIMARY_PATIENT_INSURANCE_REF": row["PRIMARYPATIENTINSURANCEID"],
        "SECONDARY_PATIENT_INSURANCE_REF": row["SECONDARYPATIENTINSURANCEID"],
        "DEPARTMENT_ID": int(row["DEPARTMENTID"]),
        # prompt schema calls this PATIENTDEPARTMENT_ID; the database does not
        "PATIENT_DEPARTMENT_ID": int(row["PATIENTDEPARTMENTID"]),
        "DIAGNOSIS_1": int(row["DIAGNOSIS1"]) if row["DIAGNOSIS1"] else None,
        "DIAGNOSIS_2": int(row["DIAGNOSIS2"]) if row["DIAGNOSIS2"] else None,
        "DIAGNOSIS_3": int(row["DIAGNOSIS3"]) if row["DIAGNOSIS3"] else None,
        "DIAGNOSIS_4": int(row["DIAGNOSIS4"]) if row["DIAGNOSIS4"] else None,
        "DIAGNOSIS_5": int(row["DIAGNOSIS5"]) if row["DIAGNOSIS5"] else None,
        "DIAGNOSIS_6": int(row["DIAGNOSIS6"]) if row["DIAGNOSIS6"] else None,
        "DIAGNOSIS_7": int(row["DIAGNOSIS7"]) if row["DIAGNOSIS7"] else None,
        "DIAGNOSIS_8": int(row["DIAGNOSIS8"]) if row["DIAGNOSIS8"] else None,
        "REFERRING_PROVIDER_REF": row["REFERRINGPROVIDERID"],
        "APPOINTMENT_REF": row["APPOINTMENTID"],
        "CURRENT_ILLNESS_DATE": row["CURRENTILLNESSDATE"],
        "SERVICE_DATE": row["SERVICEDATE"],
        "SUPERVISING_PROVIDER_REF": row["SUPERVISINGPROVIDERID"],
        "STATUS_1": row["STATUS1"],
        "STATUS_2": row["STATUS2"],
        "STATUS_P": row["STATUSP"],
        "OUTSTANDING_1": row["OUTSTANDING1"],
        "OUTSTANDING_2": row["OUTSTANDING2"],
        "OUTSTANDING_P": row["OUTSTANDINGP"],
        "LAST_BILLED_DATE_1": row["LASTBILLEDDATE1"],
        "LAST_BILLED_DATE_2": row["LASTBILLEDDATE2"],
        "LAST_BILLED_DATE_P": row["LASTBILLEDDATEP"],
        "HEALTHCARE_CLAIM_TYPE_ID_1": int(row["HEALTHCARECLAIMTYPEID1"]) if row["HEALTHCARECLAIMTYPEID1"] else None,
        "HEALTHCARE_CLAIM_TYPE_ID_2": int(row["HEALTHCARECLAIMTYPEID2"]) if row["HEALTHCARECLAIMTYPEID2"] else None,
    }


def map_claims_transactions(row):
    return {
        "CLAIM_TRANSACTION_ID": row["ID"],
        "CLAIM_REF": row["CLAIMID"],
        "CHARGE_ID": float(row["CHARGEID"]),
        "PATIENT_REF": row["PATIENTID"],
        "TYPE": row["TYPE"],
        "AMOUNT": row["AMOUNT"],
        "METHOD": row["METHOD"],
        "FROMDATE": row["FROMDATE"],
        "TODATE": row["TODATE"],
        "PLACE_OF_SERVICE": row["PLACEOFSERVICE"],
        "PROCEDURE_CODE": row["PROCEDURECODE"],
        "MODIFIER_1": row["MODIFIER1"],
        "MODIFIER_2": row["MODIFIER2"],
        "DIAGNOSIS_REF_1": row["DIAGNOSISREF1"],
        "DIAGNOSIS_REF_2": row["DIAGNOSISREF2"],
        "DIAGNOSIS_REF_3": row["DIAGNOSISREF3"],
        "DIAGNOSIS_REF_4": row["DIAGNOSISREF4"],
        "UNITS": int(row["UNITS"]),
        "DEPARTMENT_ID": row["DEPARTMENTID"],
        "NOTES": row["NOTES"],
        "UNIT_AMOUNT": row["UNITAMOUNT"],
        "TRANSFER_OUT_ID": row["TRANSFEROUTID"],
        "TRANSFER_TYPE": row["TRANSFERTYPE"],
        "PAYMENTS": row["PAYMENTS"],
        "ADJUSTMENTS": row["ADJUSTMENTS"],
        "TRANSFERS": row["TRANSFERS"],
        "OUTSTANDING": row["OUTSTANDING"],
        "APPOINTMENT_REF": row["APPOINTMENTID"],
        "LINE_NOTE": row["LINENOTE"],
        "PATIENT_INSURANCE_REF": row["PATIENTINSURANCEID"],
        # prompt schema calls this FEE_SCHEDULE_ID; the database does not
        "FEE_SCHEDULEID": row["FEESCHEDULEID"],
        "PROVIDER_REF": row["PROVIDERID"],
        "SUPERVISING_PROVIDER_REF": row["SUPERVISINGPROVIDERID"],
    }


def map_payer_transitions(row):
    return {
        "PATIENT_REF": row["PATIENT"],
        "MEMBER_ID": row["MEMBERID"],
        "START_DATE": row["START_DATE"],
        "END_DATE": row["END_DATE"],
        "PAYER_REF": row["PAYER"],
        "SECONDARY_PAYER_REF": row["SECONDARY_PAYER"],
        "PLAN_OWNERSHIP": row["PLAN_OWNERSHIP"],
        "OWNER_NAME": row["OWNER_NAME"],
    }


def map_organizations(row):
    return {
        "ORGANIZATION_ID": row["Id"],
        "NAME": row["NAME"],
        "ADDRESS": row["ADDRESS"],
        "CITY": row["CITY"],
        "STATE": row["STATE"],
        "ZIP": row["ZIP"],
        "LAT": float(row["LAT"]),
        "LON": float(row["LON"]),
        "PHONE": row["PHONE"],
        "REVENUE": float(row["REVENUE"]),
        "UTILIZATION": int(row["UTILIZATION"]),
    }


def map_providers(row):
    return {
        "PROVIDER_ID": row["Id"],
        "ORGANIZATION_REF": row["ORGANIZATION"],
        "NAME": row["NAME"],
        "GENDER": row["GENDER"],
        "SPECIALITY": row["SPECIALITY"],
        "ADDRESS": row["ADDRESS"],
        "CITY": row["CITY"],
        "STATE": row["STATE"],
        "ZIP": row["ZIP"],
        "LAT": float(row["LAT"]),
        "LON": float(row["LON"]),
        "ENCOUNTERS": int(row["ENCOUNTERS"]),
        "PROCEDURES": int(row["PROCEDURES"]),
    }


def map_payers(row):
    return {
        "PAYER_ID": row["Id"],
        "NAME": row["NAME"],
        "OWNERSHIP": row["OWNERSHIP"],
        "AMOUNT_COVERED": float(row["AMOUNT_COVERED"]),
        "AMOUNT_UNCOVERED": float(row["AMOUNT_UNCOVERED"]),
        "REVENUE": float(row["REVENUE"]),
        "COVERED_ENCOUNTERS": int(row["COVERED_ENCOUNTERS"]),
        "UNCOVERED_ENCOUNTERS": int(row["UNCOVERED_ENCOUNTERS"]),
        "COVERED_MEDICATIONS": int(row["COVERED_MEDICATIONS"]),
        "UNCOVERED_MEDICATIONS": int(row["UNCOVERED_MEDICATIONS"]),
        "COVERED_PROCEDURES": int(row["COVERED_PROCEDURES"]),
        "UNCOVERED_PROCEDURES": int(row["UNCOVERED_PROCEDURES"]),
        "COVERED_IMMUNIZATIONS": int(row["COVERED_IMMUNIZATIONS"]),
        "UNCOVERED_IMMUNIZATIONS": int(row["UNCOVERED_IMMUNIZATIONS"]),
        "UNIQUE_CUSTOMERS": int(row["UNIQUE_CUSTOMERS"]),
        "QOLS_AVG": float(row["QOLS_AVG"]),
        "MEMBER_MONTHS": int(row["MEMBER_MONTHS"]),
    }


def map_patient_expenses(row):
    return {
        "PATIENT_REF": row["PATIENT_ID"],
        "YEAR": row["YEAR"],
        "PAYER_REF": row["PAYER_ID"],
        "HEALTHCARE_EXPENSES": float(row["HEALTHCARE_EXPENSES"]),
        "INSURANCE_COSTS": float(row["INSURANCE_COSTS"]),
        "COVERED_COSTS": float(row["COVERED_COSTS"]),
    }


#: collection name -> (csv filename, mapping function)
MAPPINGS = {
    "organizations": ("organizations.csv", map_organizations),
    "payers": ("payers.csv", map_payers),
    "patients": ("patients.csv", map_patients),
    "encounters": ("encounters.csv", map_encounters),
    "procedures": ("procedures.csv", map_procedures),
    "providers": ("providers.csv", map_providers),
    "allergies": ("allergies.csv", map_allergies),
    "careplans": ("careplans.csv", map_careplans),
    "claims": ("claims.csv", map_claims),
    "claims_transactions": ("claims_transactions.csv", map_claims_transactions),
    "conditions": ("conditions.csv", map_conditions),
    "devices": ("devices.csv", map_devices),
    "imaging_studies": ("imaging_studies.csv", map_imaging_studies),
    "immunizations": ("immunizations.csv", map_immunizations),
    "medications": ("medications.csv", map_medications),
    "observations": ("observations.csv", map_observations),
    "payer_transitions": ("payer_transitions.csv", map_payer_transitions),
    "supplies": ("supplies.csv", map_supplies),
    "patient_expenses": ("patient_expenses.csv", map_patient_expenses),
}

#: Upstream ``LocalServer.collection_names``, in order. Load order is this order.
COLLECTION_NAMES = list(MAPPINGS)
