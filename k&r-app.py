import streamlit as st
import pandas as pd
from datetime import date
import re

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="K&R Database", page_icon=None, layout="wide")
st.title("K&R Database Manager")
st.caption("Upload an existing CSV or create new entries, then export. All fields are required.")

# ── Columns ───────────────────────────────────────────────────────────────────
COLUMNS = [
    "Case Name", "Origin", "Incident type", "Continent", "Country",
    "Province / State / Governorate", "District / Area / City",
    "Town / Village / Neighbourhood", "Date Taken", "Date Released",
    "Year", "Duration in Captivity (DAYS)", "Domestic / Foreign",
    "Nationality", "Sex", "Age", "Industry", "Company",
    "Number of Victims", "Insurer", "Victim Description",
    "Incident Latitude", "Incident Longitude",
    "Outcome", "Perpetrator", "Group",
    "Local Currency Code",
    "Demand Local Currency", "Demand USD",
    "Settlement USD", "Settlement Local Currency",
    "Summary", "Source", "Name",
    "Date Entered", "Source of Update", "Name Update", "Date Update",
]

INCIDENT_TYPES  = ["Kidnap for Ransom", "Express Kidnap", "Virtual Kidnap",
                   "Wrongful Detention", "Extortion", "Piracy", "Other"]
CONTINENTS      = ["Africa", "Asia", "Europe", "North America",
                   "South America", "Oceania", "Middle East"]
SEX_OPTIONS     = ["Male", "Female", "Group (Mixed)", "Unknown"]
OUTCOME_OPTIONS = ["Released", "Rescued", "Escaped", "Killed", "Unknown", "Ongoing"]
DOM_FOR         = ["Domestic", "Foreign"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def calc_duration(taken, released):
    if not taken:
        return None, None
    year = taken.year
    if released:
        if released < taken:
            return year, "INVALID"
        return year, (released - taken).days
    return year, None


def parse_coordinates(raw: str):
    raw = raw.strip()
    if not raw:
        return None, None, "Coordinates are required."
    parts = re.split(r"[,;\t]+", raw)
    if len(parts) == 1:
        parts = raw.split()
    if len(parts) != 2:
        return None, None, (
            f"Could not parse '{raw}'. Expected format: latitude, longitude "
            f"(e.g. -34.0599638580275, 18.809201667181192)"
        )
    try:
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
    except ValueError:
        return None, None, "Non-numeric value in coordinates."
    if not (-90.0 <= lat <= 90.0):
        return None, None, f"Latitude {lat} is out of range. Must be between -90 and 90."
    if not (-180.0 <= lon <= 180.0):
        return None, None, f"Longitude {lon} is out of range. Must be between -180 and 180."
    return lat, lon, None


def parse_currency(raw: str, label: str):
    """
    Parse a free-text currency amount. Strips commas, spaces, currency symbols.
    Returns (float_value, error_string).
    """
    if not raw.strip():
        return None, f"**{label}** is required."
    # Strip common formatting: currency symbols, spaces, commas
    cleaned = re.sub(r"[^\d.\-]", "", raw.strip())
    if cleaned == "" or cleaned == ".":
        return None, f"**{label}** must be a numeric value (e.g. 50000 or 50000.00)."
    try:
        value = float(cleaned)
    except ValueError:
        return None, f"**{label}** could not be parsed as a number. Received: '{raw}'."
    if value <= 0:
        return None, f"**{label}** must be greater than 0."
    return value, None


def validate_entry(f: dict) -> list:
    errors = []

    text_fields = {
        "Case Name":                      f["case_name"],
        "Origin":                         f["origin"],
        "Country":                        f["country"],
        "Province / State / Governorate": f["province"],
        "District / Area / City":         f["district"],
        "Town / Village / Neighbourhood": f["town"],
        # Victim fields (Nationality, Sex, Age, Industry, Company, Insurer,
        # Victim Description) are validated per-victim in the caller.
        "Perpetrator":                    f["perpetrator"],
        "Group":                          f["group"],
        "Summary":                        f["summary"],
        "Source":                         f["source"],
        "Analyst Name":                   f["name"],
        "Source of Update":               f["source_update"],
        "Name of Updater":                f["name_update"],
    }
    for label, val in text_fields.items():
        if not str(val).strip():
            errors.append(f"**{label}** is required.")

    # Local currency code
    if not f["currency_code"].strip():
        errors.append("**Local Currency Code** is required (e.g. ZAR, NGN, USD).")
    elif not re.match(r"^[A-Za-z]{2,4}$", f["currency_code"].strip()):
        errors.append("**Local Currency Code** must be 2–4 letters (e.g. ZAR, NGN, EUR).")

    if not f["incident_type"]:
        errors.append("**Incident Type** is required.")
    if not f["continent"]:
        errors.append("**Continent** is required.")
    if not f["dom_for"]:
        errors.append("**Domestic / Foreign** is required.")
    if not f["outcome"]:
        errors.append("**Outcome** is required.")

    if not f["date_taken"]:
        errors.append("**Date Taken** is required.")
    if not f["date_update"]:
        errors.append("**Date of Update** is required.")

    if f["outcome"] != "Ongoing" and not f["date_released"]:
        errors.append(f"**Date Released** is required when Outcome is '{f['outcome']}'.")
    if f["outcome"] == "Ongoing" and f["date_released"]:
        errors.append("**Date Released** should not be set when Outcome is 'Ongoing'.")

    if f["date_taken"] and f["date_taken"] > date.today():
        errors.append("**Date Taken** cannot be in the future.")
    if f["date_released"] and f["date_released"] > date.today():
        errors.append("**Date Released** cannot be in the future.")
    if f["date_taken"] and f["date_released"]:
        if f["date_released"] < f["date_taken"]:
            errors.append("**Date Released** cannot be earlier than **Date Taken**.")

    if f["coord_error"]:
        errors.append(f"**Incident Coordinates** — {f['coord_error']}")

    if f["num_victims"] < 1:
        errors.append("**Number of Victims** must be at least 1.")

    # Financial errors are already parsed and returned separately
    for err in f["financial_errors"]:
        errors.append(err)

    # Cross-financial logic (only if both parsed successfully)
    if f["demand_usd"] and f["settle_usd"]:
        if f["settle_usd"] > f["demand_usd"]:
            errors.append("**Settlement (USD)** cannot exceed **Demand (USD)**.")

    return errors


# ── Session state ─────────────────────────────────────────────────────────────
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame(columns=COLUMNS)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Load Existing CSV")
    uploaded = st.file_uploader("Upload a CSV file", type=["csv"])
    if uploaded:
        try:
            loaded_df = pd.read_csv(uploaded)
            for col in COLUMNS:
                if col not in loaded_df.columns:
                    loaded_df[col] = ""
            loaded_df = loaded_df[COLUMNS]
            nan_count = loaded_df.isnull().sum().sum()
            if nan_count > 0:
                st.warning(f"Loaded file contains {nan_count} empty cell(s). "
                           "Please review records in the View & Edit tab.")
            st.session_state.df = loaded_df
            st.success(f"Loaded {len(loaded_df)} records.")
        except Exception as e:
            st.error(f"Error loading file: {e}")

    st.divider()
    st.metric("Total Records", len(st.session_state.df))

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_view, tab_add, tab_export = st.tabs(["View & Edit", "Add New Entry", "Export"])

# ────────────────────────────────────────────────────────────────────────────
# TAB 1 — View & Edit
# ────────────────────────────────────────────────────────────────────────────
with tab_view:
    st.subheader("Current Records")
    if st.session_state.df.empty:
        st.info("No records yet. Upload a CSV or add a new entry.")
    else:
        nan_total   = st.session_state.df.isnull().sum().sum()
        empty_total = (st.session_state.df == "").sum().sum()
        if nan_total + empty_total > 0:
            st.warning(f"There are {nan_total + empty_total} empty cell(s) in the database. "
                       "All cells must be filled before exporting.")

        edited = st.data_editor(
            st.session_state.df,
            use_container_width=True,
            num_rows="dynamic",
            key="data_editor"
        )
        if st.button("Save Edits"):
            nan_check   = edited.isnull().sum().sum()
            empty_check = (edited == "").sum().sum()
            if nan_check + empty_check > 0:
                st.error(f"Cannot save — {nan_check + empty_check} empty cell(s) detected. "
                         "All fields must be filled.")
            else:
                st.session_state.df = edited
                st.success("Edits saved successfully.")

# ────────────────────────────────────────────────────────────────────────────
# TAB 2 — Add New Entry
# ────────────────────────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Add a New Case")
    st.info("All fields are required. No empty values are permitted.")

    # ── Number of Victims sits OUTSIDE the form so the victim fields
    #    below can re-render immediately when the value changes.
    if "num_victims" not in st.session_state:
        st.session_state.num_victims = 1

    num_victims = st.number_input(
        "Number of Victims",
        min_value=1,
        step=1,
        value=st.session_state.num_victims,
        key="num_victims_input",
        help="Set this first — victim detail fields will adjust automatically."
    )
    st.session_state.num_victims = num_victims

    with st.form("new_entry_form", clear_on_submit=True, enter_to_submit=False):

        # ── 1. Case Identification ────────────────────────────────────────────
        st.markdown("### Case Identification")
        ci1, ci2, ci3 = st.columns(3)
        with ci1:
            case_name     = st.text_input("Case Name")
            origin        = st.text_input("Origin", help="How the case was first reported or sourced")
        with ci2:
            incident_type = st.selectbox("Incident Type", [""] + INCIDENT_TYPES)
            dom_for       = st.selectbox("Domestic / Foreign", [""] + DOM_FOR,
                                         help="Was the victim domestic or foreign to the country of incident?")
        with ci3:
            # Read-only display of the victim count set above
            st.metric("Number of Victims", num_victims)
            outcome = st.selectbox("Outcome", [""] + OUTCOME_OPTIONS)

        st.divider()

        # ── 2. Dates ──────────────────────────────────────────────────────────
        st.markdown("### Dates & Captivity")
        st.caption("Year and Duration in Captivity are calculated automatically. "
                   "Date Released is required for all outcomes except 'Ongoing'.")

        dt1, dt2, dt3, dt4 = st.columns(4)
        with dt1:
            date_taken    = st.date_input("Date Taken", value=None, max_value=date.today())
        with dt2:
            date_released = st.date_input("Date Released", value=None, max_value=date.today(),
                                          help="Leave blank only if Outcome is 'Ongoing'")

        year_preview, dur_preview = calc_duration(date_taken, date_released)
        with dt3:
            st.metric("Year (auto)", year_preview if year_preview else "—")
        with dt4:
            if dur_preview == "INVALID":
                st.metric("Duration (auto)", "Date conflict")
            elif dur_preview is not None:
                st.metric("Duration (auto)", f"{dur_preview} days")
            elif date_taken and not date_released:
                st.metric("Duration (auto)", f"{(date.today()-date_taken).days}+ days (ongoing)")
            else:
                st.metric("Duration (auto)", "—")

        st.divider()

        # ── 3. Location ───────────────────────────────────────────────────────
        st.markdown("### Location")
        l1, l2, l3 = st.columns(3)
        with l1:
            continent = st.selectbox("Continent", [""] + CONTINENTS)
            country   = st.text_input("Country")
        with l2:
            province  = st.text_input("Province / State / Governorate")
            district  = st.text_input("District / Area / City")
        with l3:
            town      = st.text_input("Town / Village / Neighbourhood")

        st.markdown("**Incident Coordinates**")
        coord_raw = st.text_input(
            "Paste Coordinates",
            placeholder="-34.0599638580275, 18.809201667181192",
            help="Paste a latitude, longitude pair. Latitude and Longitude will be stored in separate columns automatically."
        )
        if coord_raw.strip():
            lat_preview, lon_preview, coord_err_preview = parse_coordinates(coord_raw)
            if coord_err_preview:
                st.warning(f"Coordinate preview: {coord_err_preview}")
            else:
                pc1, pc2, pc3 = st.columns(3)
                pc1.metric("Latitude (parsed)", f"{lat_preview:.8f}")
                pc2.metric("Longitude (parsed)", f"{lon_preview:.8f}")
                pc3.markdown(
                    f"<br><a href='https://www.google.com/maps?q={lat_preview},{lon_preview}' "
                    f"target='_blank'>Verify on Google Maps</a>",
                    unsafe_allow_html=True
                )

        st.divider()

        # ── 4. Victim Details — one section per victim ────────────────────────
        st.markdown("### Victim Details")
        st.caption(f"Enter details for each of the {int(num_victims)} victim(s) below. "
                   "Multiple values will be stored as semicolon-separated entries.")

        vic_nationalities, vic_sexes, vic_ages      = [], [], []
        vic_industries,    vic_companies, vic_insurers = [], [], []
        vic_descs = []

        for i in range(int(num_victims)):
            label = f"Victim {i + 1}" if num_victims > 1 else "Victim"
            with st.expander(label, expanded=True):
                v1, v2, v3 = st.columns(3)
                with v1:
                    vic_nationalities.append(st.text_input("Nationality",          key=f"nat_{i}"))
                    vic_sexes.append(st.selectbox("Sex", [""] + SEX_OPTIONS,        key=f"sex_{i}"))
                    vic_ages.append(st.number_input("Age", min_value=1, max_value=120,
                                                    step=1, value=1,               key=f"age_{i}"))
                with v2:
                    vic_industries.append(st.text_input("Industry",                key=f"ind_{i}",
                                                        help="e.g. Oil & Gas, NGO, Journalism"))
                    vic_companies.append(st.text_input("Company / Organisation",   key=f"comp_{i}"))
                    vic_insurers.append(st.text_input("Insurer",                   key=f"ins_{i}"))
                with v3:
                    vic_descs.append(st.text_area("Victim Description", height=120, key=f"desc_{i}"))

        st.divider()

        # ── 5. Perpetrators ───────────────────────────────────────────────────
        st.markdown("### Perpetrators")
        p1, p2 = st.columns(2)
        with p1:
            perpetrator = st.text_input("Perpetrator(s)", help="Individual names if known")
        with p2:
            group       = st.text_input("Group / Organisation", help="e.g. ISWAP, Criminal Gang")

        st.divider()

        # ── 6. Financials ─────────────────────────────────────────────────────
        st.markdown("### Financials")
        st.caption("Type amounts directly using your keyboard. "
                   "Commas and currency symbols are stripped automatically (e.g. 1,500,000 or $50000).")

        fin_row1_a, fin_row1_b = st.columns(2)
        with fin_row1_a:
            currency_code = st.text_input(
                "Local Currency Code",
                placeholder="e.g. ZAR, NGN, PHP, MXN",
                help="ISO 4217 currency code for the local currency used in this case."
            )
        with fin_row1_b:
            st.write("")  # spacer

        fin1, fin2, fin3, fin4 = st.columns(4)
        with fin1:
            demand_usd_raw   = st.text_input("Demand (USD)",                placeholder="e.g. 500000")
        with fin2:
            demand_local_raw = st.text_input("Demand (Local Currency)",     placeholder="e.g. 9500000")
        with fin3:
            settle_usd_raw   = st.text_input("Settlement (USD)",            placeholder="e.g. 250000")
        with fin4:
            settle_local_raw = st.text_input("Settlement (Local Currency)", placeholder="e.g. 4750000")

        st.divider()

        # ── 7. Summary, Source & Metadata ─────────────────────────────────────
        st.markdown("### Summary, Source & Record Metadata")
        sm1, sm2 = st.columns(2)
        with sm1:
            summary = st.text_area("Case Summary", height=150)
            source  = st.text_input("Source", help="Where this case was reported or verified")
        with sm2:
            name          = st.text_input("Analyst Name")
            date_entered  = st.date_input("Date Entered", value=date.today())
            source_update = st.text_input("Source of Update")
            name_update   = st.text_input("Name of Updater")
            date_update   = st.date_input("Date of Update", value=None)

        submitted = st.form_submit_button("Submit Entry", use_container_width=True, type="primary")

    # ── Validation & commit ───────────────────────────────────────────────────
    if submitted:
        lat_final, lon_final, coord_error = parse_coordinates(coord_raw)

        demand_usd_val,   err_demand_usd   = parse_currency(demand_usd_raw,   "Demand (USD)")
        demand_local_val, err_demand_local = parse_currency(demand_local_raw, "Demand (Local Currency)")
        settle_usd_val,   err_settle_usd   = parse_currency(settle_usd_raw,   "Settlement (USD)")
        settle_local_val, err_settle_local = parse_currency(settle_local_raw, "Settlement (Local Currency)")

        financial_errors = [e for e in [
            err_demand_usd, err_demand_local, err_settle_usd, err_settle_local
        ] if e]

        # Validate each victim's fields
        victim_errors = []
        for i in range(int(num_victims)):
            label = f"Victim {i+1}" if num_victims > 1 else "Victim"
            if not vic_nationalities[i].strip():
                victim_errors.append(f"**{label} — Nationality** is required.")
            if not vic_sexes[i]:
                victim_errors.append(f"**{label} — Sex** is required.")
            if vic_ages[i] < 1:
                victim_errors.append(f"**{label} — Age** must be 1 or greater.")
            if not vic_industries[i].strip():
                victim_errors.append(f"**{label} — Industry** is required.")
            if not vic_companies[i].strip():
                victim_errors.append(f"**{label} — Company** is required.")
            if not vic_insurers[i].strip():
                victim_errors.append(f"**{label} — Insurer** is required.")
            if not vic_descs[i].strip():
                victim_errors.append(f"**{label} — Victim Description** is required.")

        field_data = {
            "case_name":        case_name,
            "origin":           origin,
            "incident_type":    incident_type,
            "continent":        continent,
            "country":          country,
            "province":         province,
            "district":         district,
            "town":             town,
            "coord_error":      coord_error,
            "dom_for":          dom_for,
            "outcome":          outcome,
            "date_taken":       date_taken,
            "date_released":    date_released,
            "date_update":      date_update,
            # Pass dummy values for victim fields — validated above separately
            "nationality":      "validated_separately",
            "sex":              "validated_separately",
            "age":              1,
            "industry":         "validated_separately",
            "company":          "validated_separately",
            "insurer":          "validated_separately",
            "vic_desc":         "validated_separately",
            "perpetrator":      perpetrator,
            "group":            group,
            "num_victims":      num_victims,
            "currency_code":    currency_code,
            "demand_usd":       demand_usd_val,
            "demand_local":     demand_local_val,
            "settle_usd":       settle_usd_val,
            "settle_local":     settle_local_val,
            "financial_errors": financial_errors,
            "summary":          summary,
            "source":           source,
            "name":             name,
            "source_update":    source_update,
            "name_update":      name_update,
        }

        errors = validate_entry(field_data) + victim_errors

        if errors:
            st.error(f"{len(errors)} issue(s) found. Please fix the following before submitting:")
            for err in errors:
                st.markdown(f"- {err}")
        else:
            year_final, dur_final = calc_duration(date_taken, date_released)
            if dur_final is None and date_taken:
                dur_final = (date.today() - date_taken).days

            # Join multi-victim fields with semicolons
            sep = " ; "
            new_row = {
                "Case Name":                      case_name.strip(),
                "Origin":                         origin.strip(),
                "Incident type":                  incident_type,
                "Continent":                      continent,
                "Country":                        country.strip(),
                "Province / State / Governorate": province.strip(),
                "District / Area / City":         district.strip(),
                "Town / Village / Neighbourhood": town.strip(),
                "Date Taken":                     str(date_taken),
                "Date Released":                  str(date_released) if date_released else "Ongoing",
                "Year":                           year_final,
                "Duration in Captivity (DAYS)":   dur_final,
                "Domestic / Foreign":             dom_for,
                "Nationality":                    sep.join(v.strip() for v in vic_nationalities),
                "Sex":                            sep.join(vic_sexes),
                "Age":                            sep.join(str(a) for a in vic_ages),
                "Industry":                       sep.join(v.strip() for v in vic_industries),
                "Company":                        sep.join(v.strip() for v in vic_companies),
                "Number of Victims":              int(num_victims),
                "Insurer":                        sep.join(v.strip() for v in vic_insurers),
                "Victim Description":             sep.join(v.strip() for v in vic_descs),
                "Incident Latitude":              lat_final,
                "Incident Longitude":             lon_final,
                "Outcome":                        outcome,
                "Perpetrator":                    perpetrator.strip(),
                "Group":                          group.strip(),
                "Local Currency Code":            currency_code.strip().upper(),
                "Demand Local Currency":          demand_local_val,
                "Demand USD":                     demand_usd_val,
                "Settlement USD":                 settle_usd_val,
                "Settlement Local Currency":      settle_local_val,
                "Summary":                        summary.strip(),
                "Source":                         source.strip(),
                "Name":                           name.strip(),
                "Date Entered":                   str(date_entered),
                "Source of Update":               source_update.strip(),
                "Name Update":                    name_update.strip(),
                "Date Update":                    str(date_update),
            }

            st.session_state.df = pd.concat(
                [st.session_state.df, pd.DataFrame([new_row])], ignore_index=True
            )
            # Reset victim count after successful submission
            st.session_state.num_victims = 1
            st.success(
                f"'{case_name}' added successfully. "
                f"{int(num_victims)} victim(s) | Year: {year_final} | Duration: {dur_final} day(s) | "
                f"Demand: {currency_code.upper()} {demand_local_val:,.2f} / USD {demand_usd_val:,.2f}"
                + (" (ongoing at time of entry)" if outcome == "Ongoing" else "")
            )

# ────────────────────────────────────────────────────────────────────────────
# TAB 3 — Export
# ────────────────────────────────────────────────────────────────────────────
with tab_export:
    st.subheader("Export Database")
    if st.session_state.df.empty:
        st.info("Nothing to export yet.")
    else:
        nan_total   = st.session_state.df.isnull().sum().sum()
        empty_total = (st.session_state.df == "").sum().sum()

        if nan_total + empty_total > 0:
            st.error(f"Export blocked — {nan_total + empty_total} empty cell(s) detected. "
                     "Go to View & Edit to resolve them before exporting.")
        else:
            csv_data = st.session_state.df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download as CSV",
                data=csv_data,
                file_name=f"KR_Database_Export_{date.today()}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.dataframe(st.session_state.df, use_container_width=True)