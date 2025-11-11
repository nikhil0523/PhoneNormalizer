import streamlit as st
import pandas as pd
import re
import os
from io import BytesIO
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat
import base64


# ============================================================
# PAGE SETUP + BANNER
# ============================================================
st.set_page_config(page_title="📞 Phone Number Normalizer", layout="wide")

# Load top banner
with open("em eminenture.jpg", "rb") as f:
    banner_base64 = base64.b64encode(f.read()).decode()

st.markdown(
    f"""
    <style>
        .stApp {{
            background-color: #0E1117 !important;
        }}

        /* Banner container */
        #custom-banner {{
            width: 100%;
            display: flex !important;
            justify-content: flex-start !important;
            align-items: flex-start;
            margin-top: 10px;
            margin-left: 40px;
        }}

        /* Banner image — MAKING IT BIGGER & WIDE */
        #custom-banner img {{
            width: 900px;      /* Increased width */
            max-width: 95%;    /* Prevent overflow */
            height: auto;
            border-radius: 10px;
            box-shadow: 0px 4px 18px rgba(0,0,0,0.45);
        }}

        /* Content wrapper */
        #content-wrapper {{
            margin-top: 30px;
            margin-left: 40px;
        }}

        /* Responsive layout */
        @media (max-width: 900px) {{
            #custom-banner {{
                margin-left: 0;
                justify-content: center !important;
            }}
            #custom-banner img {{
                width: 100%;
                max-width: 100%;
            }}
            #content-wrapper {{
                margin-left: 10px;
            }}
        }}
    </style>
    <div id="custom-banner">
        <img src="data:image/jpg;base64,{banner_base64}">
    </div>
    <div id="content-wrapper">
    """,
    unsafe_allow_html=True
)

# ============================================================
# INTERNAL COUNTRY CODES
# ============================================================
@st.cache_data
def load_internal_country_codes():
    import pycountry
    from phonenumbers.phonenumberutil import country_code_for_region

    data = []
    for c in pycountry.countries:
        try:
            code = country_code_for_region(c.alpha_2)
            if code:
                data.append({"Country": c.name.lower(), "Dialing": str(code)})
        except:
            pass
    df = pd.DataFrame(data)
    return dict(zip(df["Country"], df["Dialing"])), set(df["Dialing"])


internal_codes, internal_all = load_internal_country_codes()

# ============================================================
# EXTERNAL COUNTRY CODES
# ============================================================
@st.cache_data
def load_external_country_codes(path):
    try:
        if not os.path.exists(path):
            return {}, set()

        df = pd.read_excel(path)

        possible = [
            "International dialing", "Dialing Code", "Dialing code",
            "Code", "Country Code", "International Dialing Code",
            "Phone Code", "Phone code", "Dial Code"
        ]

        dial_col = None
        for col in df.columns:
            if col.strip() in possible:
                dial_col = col
                break

        if not dial_col:
            return {}, set()

        df["Dialing"] = df[dial_col].astype(str).str.replace(r"\D", "", regex=True)
        df["Country_clean"] = df["Country"].astype(str).str.strip().str.lower()

        return dict(zip(df["Country_clean"], df["Dialing"])), set(df["Dialing"])

    except:
        return {}, set()


#COUNTRY_CODES_FILE = r"C:\Users\nikhi\Downloads\Country_codes.xlsx"
COUNTRY_CODES_FILE = os.path.join(os.path.dirname(__file__), "Country_codes.xlsx")
external_codes, external_all = load_external_country_codes(COUNTRY_CODES_FILE)


# ============================================================
# CARIBBEAN COUNTRIES (NANP +1)
# ============================================================
caribbean = {
    "antigua and barbuda", "bahamas", "the bahamas", "barbados", "cuba",
    "dominica", "dominican republic", "grenada", "haiti", "jamaica",
    "saint kitts and nevis", "st kitts and nevis", "saint lucia",
    "st lucia", "saint vincent and the grenadines",
    "st vincent and the grenadines", "trinidad and tobago"
}

# ============================================================
# EXPECTED NATIONAL LENGTHS
# ============================================================
expected_lengths = {
    "usa": 10, "united states": 10, "canada": 10, **{c: 10 for c in caribbean},
    "united kingdom": 10, "mexico": 10, "india": 10,
    "australia": 9, "new zealand": 8, "brazil": 10
}

# ============================================================
# IMPROVED COMPARISON LOGIC
# ============================================================
def compute_comparison(original, corrected):
    orig = str(original).strip()
    corr = str(corrected).strip()

    if orig == corr:
        return "Unchanged"

    # Detect duplicate 868 fix
    if "868" in orig and "(868)" in corr:
        return "Removed duplicated 868 prefix + reformatted"

    if corr.startswith("+1-(") and not orig.startswith("+1"):
        return "Added +1 + reformatted into NANP"

    if corr.startswith("+44") and not orig.startswith("+44"):
        return "Added +44 + UK formatting"

    if corr.startswith("+91") and not orig.startswith("+91"):
        return "Added +91 + India formatting"

    if corr.startswith("+52") and not orig.startswith("+52"):
        return "Added +52 + Mexico formatting"

    if corr.startswith("+55") and not orig.startswith("+55"):
        return "Added +55 + Brazil formatting"

    # Formatting changed only
    if re.sub(r"\D", "", orig) == re.sub(r"\D", "", corr):
        return "Formatting changed only"

    # Digit trimming
    if len(re.sub(r"\D", "", orig)) > len(re.sub(r"\D", "", corr)):
        return "Trimmed extra digits"

    return "Changed digits"


# ============================================================
# FORMAT BY COUNTRY
# ============================================================
def format_by_country(e164, country):
    digits = re.sub(r"\D", "", e164)
    c = country.lower()

    if c in ["uk", "gb", "united kingdom"]:
        n = digits[2:] if digits.startswith("44") else digits
        return f"+44-{n[:4]}-{n[4:7]}-{n[7:]}"

    if c == "india":
        n = digits[2:] if digits.startswith("91") else digits
        return f"+91-{n[:2]}-{n[2:]}"

    if c == "mexico":
        n = digits[2:] if digits.startswith("52") else digits
        return f"+52-{n[:3]}-{n[3:6]}-{n[6:]}"

    if c == "brazil":
        n = digits[2:] if digits.startswith("55") else digits
        return f"+55-{n[:2]}-{n[2:6]}-{n[6:]}"

    return e164


# ============================================================
# NORMALIZE NUMBER
# ============================================================
def normalize_number(number, country_clean):

    if not number or pd.isna(number) or not re.search(r"\d", str(number)):
        return "", "Missing Number", "Missing Number"

    original = str(number)
    c = str(country_clean).lower().strip()

    if c in ["uk", "gb", "u.k.", "unitedkingdom"]:
        c = "united kingdom"

    correct_code = internal_codes.get(c) or external_codes.get(c)
    if not correct_code:
        return number, "❌ Unknown country", "Unknown country"

    digits = re.sub(r"\D", "", original)

    # -------------------------------
    # NANP LOGIC
    # -------------------------------
    if c in ["united states", "usa", "canada"] or c in caribbean:

        cleaned = digits

        # Trinidad double-868 fix
        if c == "trinidad and tobago" and cleaned.startswith("1868868") and len(cleaned) > 11:
            local7 = cleaned[-7:]
            out = f"+1-(868)-{local7[:3]}-{local7[3:]}"
            return out, "✅ Valid & Matched", compute_comparison(original, out)

        # try parsing
        def try_parse(n):
            try:
                p = phonenumbers.parse(n, "US")
                if phonenumbers.is_valid_number(p):
                    return phonenumbers.format_number(p, PhoneNumberFormat.E164)
            except:
                return None

        e164 = try_parse(original) or try_parse("+" + cleaned)

        if e164:
            d = re.sub(r"\D", "", e164)
            nat = d[-10:]
            out = f"+1-({nat[:3]})-{nat[3:6]}-{nat[6:]}"
            return out, "✅ Valid & Matched", compute_comparison(original, out)

        cleaned = cleaned[-10:]
        out = f"+1-({cleaned[:3]})-{cleaned[3:6]}-{cleaned[6:]}"
        return out, "⚠️ Forced into US format", compute_comparison(original, out)

    # -------------------------------
    # NON-NANP LOGIC
    # -------------------------------
    corrected = f"+{correct_code}{digits}" if not digits.startswith(correct_code) else f"+{digits}"
    formatted = format_by_country(corrected, c)

    comp = compute_comparison(original, formatted)

    # length check
    expected = expected_lengths.get(c)
    if expected:
        if len(re.sub(r"\D", "", formatted)) < len(correct_code) + expected:
            return formatted, "Missing Data", comp

    return formatted, "✅ Valid & Matched", comp


# ============================================================
# TITLE TEXT
# ============================================================
st.markdown(
    """
    <h1 style="font-size:38px; font-weight:700;">
        📞 Phone Number Normalizer
    </h1>

    <p style="font-size:18px; max-width:650px;">
        Upload a file containing <b>Zip/PostalCode</b>, <b>Phone Number</b>, and <b>Country</b>.<br>
        The app will clean, validate, correct, and format numbers.
    </p>
    """,
    unsafe_allow_html=True
)

# ============================================================
# FILE UPLOAD
# ============================================================
st.subheader("📁 Upload Your File")

uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx"])

if uploaded:
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

    df["Country_clean"] = df["Country"].astype(str).str.strip().str.lower()

    df[["Corrected Number", "Verification", "Comparison"]] = df.apply(
        lambda x: pd.Series(normalize_number(x["Phone Number"], x["Country_clean"])),
        axis=1
    )

    st.success("✅ Normalization complete!")
    st.dataframe(df)

    # Downloads
    csv_data = df.to_csv(index=False).encode("utf-8")
    ex_buffer = BytesIO()
    with pd.ExcelWriter(ex_buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False)
    st.download_button("⬇️ Download CSV", csv_data, "normalized.csv")
    st.download_button("⬇️ Download Excel", ex_buffer.getvalue(), "normalized.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("</div>", unsafe_allow_html=True)
