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
The app will automatically clean, validate, and correct phone numbers.  
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
# Load external backup country codes (static developer file)
# ---------------------------
@st.cache_data
def load_external_country_codes(file_path):
    try:
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
# Normalize phone number
# ---------------------------
def normalize_number(number: str, country_clean: str):
    correct_code = internal_country_to_dialing.get(country_clean)
    if not correct_code:
        correct_code = external_country_to_dialing.get(country_clean)

    if not correct_code:
        return number, "❌ Unknown country"

    digits = "".join(c for c in str(number) if c.isdigit())

    # 🇺🇸 Special handling for USA
    if country_clean in ["united states", "usa"]:
        try:
            cleaned = re.sub(r"[^\d]", "", str(number))
            has_plus = str(number).strip().startswith("+")
            region_hint = "US"

            def try_parse(num):
                try:
                    parsed = phonenumbers.parse(num, region_hint)
                    if phonenumbers.is_valid_number_for_region(parsed, region_hint):
                        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
                except NumberParseException:
                    return None
                return None

            formatted = try_parse(number)
            if formatted:
                if has_plus:
                    return formatted, "✅ Valid & Matched"
                return formatted, f"⚠️ Added country code → {correct_code}"

            formatted = try_parse("+" + cleaned)
            if formatted:
                if not has_plus:
                    return formatted, f"⚠️ Added country code → {correct_code}"
                return formatted, "✅ Valid & Matched"

            if cleaned.startswith("001"):
                corrected = f"+1{cleaned[3:]}"
                formatted = try_parse(corrected)
                if formatted:
                    return formatted, f"⚠️ Added country code → {correct_code}"

            if cleaned.startswith("1"):
                cleaned = cleaned[1:]
            cleaned = cleaned[-10:]
            corrected = f"+1{cleaned}"
            formatted = try_parse(corrected)
            if formatted:
                return formatted, "⚠️ Forced into US format"
            return corrected, "⚠️ Forced into US format"

        except Exception:
            pass

    # 🌍 Default logic for all other countries
    matched_code = None
    for code in sorted(internal_all_codes.union(external_all_codes), key=lambda x: -len(x)):
        if digits.startswith(code):
            matched_code = code
            break

    # ✅ Improved correction logic to avoid over-trimming
    if matched_code:
        remaining_digits = digits[len(matched_code):]

        # Handle +1-based codes incorrectly mapped to another country
        if matched_code.startswith("1") and correct_code != "1":
            remaining_digits = digits[len("1"):]

        if matched_code == correct_code:
            corrected_number = f"+{digits}"
            verification = "✅ Valid & Matched"
        elif matched_code != correct_code:
            corrected_number = f"+{correct_code}{remaining_digits}"
            verification = f"🔄 Corrected from {matched_code} → {correct_code}"
    else:
        digits = digits.lstrip("0")
        corrected_number = f"+{correct_code}{digits}"
        verification = f"⚠️ Added country code → {correct_code}"

    return corrected_number, verification

# ---------------------------
# File uploader
# ---------------------------
st.subheader("📂 Upload Your File")
uploaded_data = st.file_uploader("Upload CSV or Excel with Zip/PostalCode, Phone Number, and Country", type=["csv", "xlsx"])

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

            st.download_button("⬇️ Download CSV", data=csv_data, file_name="normalized_numbers.csv", mime="text/csv")
            st.download_button("⬇️ Download Excel", data=excel_data, file_name="normalized_numbers.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"❌ Error reading file: {e}")
else:
    st.info("👆 Upload your input file above to start normalization.")