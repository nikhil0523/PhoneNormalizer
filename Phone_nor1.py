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
    "antigua and barbuda", "the bahamas", "bahamas", "barbados", "cuba",
    "dominica", "dominican republic", "grenada", "haiti", "jamaica",
    "saint kitts and nevis", "st kitts and nevis", "saint lucia", "st lucia",
    "saint vincent and the grenadines", "st vincent and the grenadines", "trinidad and tobago",
}


# ---------------------------
# Expected national number lengths per country
# ---------------------------
expected_lengths = {
    "usa": 10, "united states": 10, "canada": 10, **{c: 10 for c in caribbean_countries},
    "united kingdom": 10, "uk": 10, "gb": 10, "mexico": 10,
    "australia": 9, "new zealand": 8, "india": 10, "brazil": 10,
}


# ---------------------------
# Format by country
# ---------------------------
def format_by_country(e164_number: str, country_clean: str):
    digits = re.sub(r"\D", "", e164_number)
    if not digits:
        return e164_number

    # normalize variants
    normalized = country_clean.strip().lower()
    if normalized in ["uk", "u.k.", "unitedkingdom", "gb"]:
        normalized = "united kingdom"

    # 🇺🇸 NANP format (US, Canada, Caribbean)
    if (
        normalized in ["united states", "usa", "canada"]
        or normalized in caribbean_countries
    ):
        national = digits[-10:]
        return f"+1-({national[:3]})-{national[3:6]}-{national[6:]}"

    # 🇬🇧 United Kingdom
    elif normalized == "united kingdom":
        national = digits[2:] if digits.startswith("44") else digits
        if len(national) >= 10:
            part1 = national[:4]
            part2 = national[4:7]
            part3 = national[7:]
            return f"+44-{part1}-{part2}-{part3}"
        else:
            return f"+44-{national}"

    # 🇲🇽 Mexico
    elif normalized == "mexico":
        national = digits[2:] if digits.startswith("52") else digits
        return f"+52-{national[:3]}-{national[3:6]}-{national[6:]}"

    # 🇮🇳 India
    elif normalized == "india":
        national = digits[2:] if digits.startswith("91") else digits
        if len(national) >= 10:
            std = national[:2]
            rest = national[2:]
            return f"+91-{std}-{rest}"
        else:
            return f"+91-{national}"

    # 🇧🇷 Brazil
    elif normalized == "brazil":
        national = digits[2:] if digits.startswith("55") else digits
        return f"+55-{national[:2]}-{national[2:6]}-{national[6:]}"

    # 🇦🇺 Australia
    elif normalized == "australia":
        national = digits[2:] if digits.startswith("61") else digits
        return f"+61-{national[:1]}-{national[1:5]}-{national[5:]}"

    # 🇳🇿 New Zealand
    elif normalized == "new zealand":
        national = digits[2:] if digits.startswith("64") else digits
        return f"+64-{national[:1]}-{national[1:4]}-{national[4:]}"

    # fallback
    else:
        return e164_number


# ---------------------------
# Normalize and Validate
# ---------------------------
def normalize_number(number: str, country_clean: str):
    if not number or pd.isna(number) or not re.search(r"\d", str(number)):
        return "", "Missing Number"

    normalized_country = str(country_clean).strip().lower()
    if normalized_country in ["uk", "u.k.", "unitedkingdom", "gb"]:
        normalized_country = "united kingdom"

    correct_code = (
        internal_country_to_dialing.get(normalized_country)
        or external_country_to_dialing.get(normalized_country)
    )
    if not correct_code:
        return number, "❌ Unknown country"

    digits = re.sub(r"\D", "", str(number))
    if not digits:
        return number, "Missing Number"

    # Generate corrected E.164-style number
    if not digits.startswith(correct_code):
        corrected_number = f"+{correct_code}{digits}"
    else:
        corrected_number = f"+{digits}"

    formatted = format_by_country(corrected_number, normalized_country)

    # ✅ Validate expected length — show "Missing Data" if short, but keep number
    digits_only = re.sub(r"\D", "", formatted)
    expected_len = expected_lengths.get(normalized_country)
    if expected_len and len(digits_only) < (len(correct_code) + expected_len):
        return formatted, "Missing Data"

    return formatted, "✅ Valid & Matched"


# ---------------------------
# Streamlit file uploader
# ---------------------------
st.subheader("📂 Upload Your File")
uploaded_data = st.file_uploader(
    "Upload CSV or Excel with Zip/PostalCode, Phone Number, and Country",
    type=["csv", "xlsx"]
)

if uploaded_data:
    try:
        df = pd.read_csv(uploaded_data) if uploaded_data.name.endswith(".csv") else pd.read_excel(uploaded_data)
        st.write("### Sample Data")
        st.dataframe(df.head())

        required_cols = {"Zip/PostalCode", "Phone Number", "Country"}
        if not required_cols.issubset(df.columns):
            st.error(f"❌ The file must contain columns: {', '.join(required_cols)}")
        else:
            df["Country_clean"] = df["Country"].astype(str).str.strip().str.lower()
            df[["Corrected Number", "Verification"]] = df.apply(
                lambda x: pd.Series(normalize_number(x["Phone Number"], x["Country_clean"])), axis=1
            )

            st.success("✅ Normalization complete!")
            st.dataframe(df[["Zip/PostalCode", "Phone Number", "Country", "Corrected Number", "Verification"]])

            csv_data = df.to_csv(index=False).encode("utf-8")
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Normalized")
            excel_data = excel_buffer.getvalue()

            st.download_button("⬇️ Download CSV", data=csv_data, file_name="normalized_numbers.csv", mime="text/csv")
            st.download_button(
                "⬇️ Download Excel",
                data=excel_data,
                file_name="normalized_numbers.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        st.error(f"❌ Error reading file: {e}")
else:
    st.info("👆 Upload your input file above to start normalization.")
