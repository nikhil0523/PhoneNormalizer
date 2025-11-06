import streamlit as st
import pandas as pd
import re
import os
from io import BytesIO
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat


# ---------------------------
# Page setup
# ---------------------------
st.set_page_config(page_title="📞 Phone Number Normalizer", layout="centered")
st.title("📞 Phone Number Normalizer")
st.markdown("""
Upload a file containing **Zip/PostalCode**, **Phone Number**, and **Country** columns.  
The app will automatically clean, validate, correct, and format phone numbers.  
It uses internal country codes and a backup `Country_codes.xlsx` file.
""")


# ---------------------------
# Load internal country codes
# ---------------------------
@st.cache_data
def load_internal_country_codes():
    import pycountry
    from phonenumbers.phonenumberutil import country_code_for_region

    data = []
    for country in pycountry.countries:
        try:
            code = country_code_for_region(country.alpha_2)
            if code:
                data.append({"Country": country.name.lower(), "Dialing clean": str(code)})
        except Exception:
            pass
    d1 = pd.DataFrame(data)
    country_to_dialing = dict(zip(d1["Country"], d1["Dialing clean"]))
    all_codes = set(filter(None, d1["Dialing clean"].tolist()))
    return country_to_dialing, all_codes


internal_country_to_dialing, internal_all_codes = load_internal_country_codes()


# ---------------------------
# Load external backup country codes
# ---------------------------
@st.cache_data
def load_external_country_codes(file_path):
    try:
        if not os.path.exists(file_path):
            st.warning("⚠️ Country_codes.xlsx not found. Using only internal country codes.")
            return {}, set()

        d1 = pd.read_excel(file_path)
        possible_dial_cols = [
            "International dialing", "Dialing Code", "Dialing code",
            "Code", "Country Code", "International Dialing Code",
            "Phone Code", "Phone code", "Dial Code"
        ]
        dial_col = None
        for col in d1.columns:
            if col.strip() in possible_dial_cols:
                dial_col = col
                break
        if not dial_col:
            st.warning(f"⚠️ No valid dialing code column found in {file_path}")
            return {}, set()

        d1["Dialing clean"] = d1[dial_col].astype(str).str.replace(r"\D", "", regex=True)
        d1["Country_clean"] = d1["Country"].astype(str).str.strip().str.lower()
        external_country_to_dialing = dict(zip(d1["Country_clean"], d1["Dialing clean"]))
        all_codes = set(filter(None, d1["Dialing clean"].tolist()))
        return external_country_to_dialing, all_codes

    except Exception as e:
        st.error(f"❌ Error loading Country_codes.xlsx: {e}")
        return {}, set()


#COUNTRY_CODES_FILE = "C:\\Users\\nikhi\\Downloads\\Country_codes.xlsx"
COUNTRY_CODES_FILE = os.path.join(os.path.dirname(__file__), "Country_codes.xlsx")
external_country_to_dialing, external_all_codes = load_external_country_codes(COUNTRY_CODES_FILE)


# ---------------------------
# Caribbean countries under NANP (+1)
# ---------------------------
caribbean_countries = {
    "antigua and barbuda",
    "the bahamas",
    "bahamas",
    "barbados",
    "cuba",
    "dominica",
    "dominican republic",
    "grenada",
    "haiti",
    "jamaica",
    "saint kitts and nevis",
    "st kitts and nevis",
    "saint lucia",
    "st lucia",
    "saint vincent and the grenadines",
    "st vincent and the grenadines",
    "trinidad and tobago",
}


# ---------------------------
# Formatting rules by country
# ---------------------------
def format_by_country(e164_number: str, country_clean: str):
    """Apply post-formatting rules based on company standards."""
    digits = re.sub(r"\D", "", e164_number)
    if not digits:
        return e164_number

    # NANP: US, Canada, Caribbean (+1)
    if (
        country_clean in ["united states", "usa", "canada"]
        or country_clean in caribbean_countries
    ):
        national = digits[-10:]
        return f"+1-({national[:3]})-{national[3:6]}-{national[6:]}"

    elif country_clean == "united kingdom":
        national = digits[2:] if digits.startswith("44") else digits
        return f"+44-{national[:4]}-{national[4:7]}-{national[7:]}"

    elif country_clean == "mexico":
        national = digits[2:] if digits.startswith("52") else digits
        return f"+52-{national[:3]}-{national[3:6]}-{national[6:]}"

    elif country_clean == "australia":
        national = digits[2:] if digits.startswith("61") else digits
        return f"+61-{national[:1]}-{national[1:5]}-{national[5:]}"

    elif country_clean == "new zealand":
        national = digits[2:] if digits.startswith("64") else digits
        return f"+64-{national[:1]}-{national[1:4]}-{national[4:]}"

    elif country_clean == "india":
        national = digits[2:] if digits.startswith("91") else digits
        if len(national) >= 10:
            std = national[:2]
            rest = national[2:]
            return f"+91-{std}-{rest}"
        else:
            return f"+91-{national}"

    elif country_clean == "brazil":
        national = digits[2:] if digits.startswith("55") else digits
        return f"+55-{national[:2]}-{national[2:6]}-{national[6:]}"

    else:
        # fallback – return unchanged E.164
        return e164_number


# ---------------------------
# Normalize phone number
# ---------------------------
def normalize_number(number: str, country_clean: str):
    # Handle missing or empty numbers
    if not number or pd.isna(number) or not re.search(r"\d", str(number)):
        return "", "Missing Number"

    correct_code = internal_country_to_dialing.get(country_clean)
    if not correct_code:
        correct_code = external_country_to_dialing.get(country_clean)
    if not correct_code:
        return "", "❌ Unknown country"

    digits = "".join(c for c in str(number) if c.isdigit())

    # 🇺🇸 Special handling for NANP (USA/Canada/Caribbean)
    if (
        country_clean in ["united states", "usa", "canada"]
        or country_clean in caribbean_countries
    ):
        try:
            cleaned = re.sub(r"[^\d+]", "", str(number))
            if not cleaned.startswith("+"):
                cleaned = "+" + cleaned

            try:
                parsed = phonenumbers.parse(cleaned, "US")
            except NumberParseException:
                parsed = None

            if parsed and phonenumbers.is_valid_number(parsed):
                if parsed.country_code == 1:
                    formatted = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
                    display = format_by_country(formatted, country_clean)
                    return display, "✅ Valid & Matched"
                else:
                    national = str(parsed.national_number)
                    corrected = f"+1{national}"
                    display = format_by_country(corrected, country_clean)
                    return display, "⚠️ Forced into US/Caribbean format"

            # Manual fallback
            digits = re.sub(r"\D", "", cleaned)
            if not digits:
                return "", "Missing Number"

            if digits.startswith("1") and len(digits) == 11:
                formatted = f"+{digits}"
                display = format_by_country(formatted, country_clean)
                return display, "✅ Valid & Matched"
            if len(digits) == 10:
                formatted = f"+1{digits}"
                display = format_by_country(formatted, country_clean)
                return display, "✅ Valid & Matched"
            if len(digits) < 10:
                return "", "Missing Number"

            corrected = f"+1{digits[-10:]}"
            display = format_by_country(corrected, country_clean)
            return display, "⚠️ Forced into US/Caribbean format"

        except Exception:
            return "", "Missing Number"

    # 🌍 Default logic for all other countries
    matched_code = None
    for code in sorted(internal_all_codes.union(external_all_codes), key=lambda x: -len(x)):
        if digits.startswith(code):
            matched_code = code
            break

    if not digits:
        return "", "Missing Number"

    if matched_code:
        remaining_digits = digits[len(matched_code):]
        if matched_code.startswith("1") and correct_code != "1":
            remaining_digits = digits[len("1"):]
        if matched_code == correct_code:
            corrected_number = f"+{digits}"
            verification = "✅ Valid & Matched"
        else:
            corrected_number = f"+{correct_code}{remaining_digits}"
            verification = f"🔄 Corrected from {matched_code} → {correct_code}"
    else:
        digits = digits.lstrip("0")
        if not digits:
            return "", "Missing Number"
        corrected_number = f"+{correct_code}{digits}"
        verification = f"⚠️ Added country code → {correct_code}"

    display = format_by_country(corrected_number, country_clean)
    return display, verification


# ---------------------------
# File uploader
# ---------------------------
st.subheader("📂 Upload Your File")
uploaded_data = st.file_uploader(
    "Upload CSV or Excel with Zip/PostalCode, Phone Number, and Country",
    type=["csv", "xlsx"]
)

if uploaded_data:
    try:
        if uploaded_data.name.endswith(".csv"):
            df = pd.read_csv(uploaded_data)
        else:
            df = pd.read_excel(uploaded_data)

        st.write("### Sample Data")
        st.dataframe(df.head())

        required_cols = {"Zip/PostalCode", "Phone Number", "Country"}
        if not required_cols.issubset(df.columns):
            st.error(f"❌ The file must contain columns: {', '.join(required_cols)}")
        else:
            df["Country_clean"] = df["Country"].astype(str).str.strip().str.lower()
            df[["Corrected Number", "Verification"]] = df.apply(
                lambda x: pd.Series(normalize_number(x["Phone Number"], x["Country_clean"])),
                axis=1
            )

            st.success("✅ Normalization complete!")
            st.dataframe(df[["Zip/PostalCode", "Phone Number", "Country", "Corrected Number", "Verification"]])

            csv_data = df.to_csv(index=False).encode("utf-8")
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Normalized")
            excel_data = excel_buffer.getvalue()

            st.download_button(
                "⬇️ Download CSV",
                data=csv_data,
                file_name="normalized_numbers.csv",
                mime="text/csv"
            )
            st.download_button(
                "⬇️ Download Excel",
                data=excel_data,
                file_name="normalized_numbers.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"❌ Error reading file: {e}")
else:
    st.info("👆 Upload your input file above to start normalization.")
