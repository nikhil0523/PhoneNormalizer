# Phone Normalizer

A **Streamlit app** that standardizes and validates phone numbers for multiple countries. Upload a CSV or Excel file containing phone numbers and countries, and the app will automatically correct, validate, and add missing country codes.

---

## **Features**

- Automatically **add or correct country codes**  
- **Validate** numbers against known country dialing codes  
- Provide a **verification status**: ✅ valid, 🔄 corrected, ⚠️ added code, ❌ unknown country  
- Download the results as **Excel** or **CSV**  
- Works with **CSV** and **Excel** input files  

---

## **Input File Requirements**

The uploaded file must contain the following columns:  

- `Phone Number`  
- `Country`
- `Zip/PostalCode`

---

## **Output**

The app will add the following columns:  

- `Corrected Number`  
- `Verification`  
