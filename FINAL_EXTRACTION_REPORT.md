# Bank FD Rates Extraction - Final Report

**Date:** May 5, 2026  
**Extraction Duration:** 82.58 seconds (1.4 minutes)

---

## Executive Summary

Successfully extracted Fixed Deposit (FD) interest rates from **18 out of 30 Indian banks** (60% success rate), collecting a total of **209 FD rate entries** for deposits less than ₹3 Crore.

---

## Overall Statistics

| Metric | Value |
|--------|-------|
| **Total Banks Processed** | 30 |
| **Successful Extractions** | 18 (60%) |
| **Failed Extractions** | 12 (40%) |
| **Total Rates Extracted** | 209 |
| **Average Rates per Bank** | 11.6 rates |

---

## Successfully Extracted Banks (18 Banks)

| # | Bank Name | Rates Extracted | Custom Parser |
|---|-----------|-----------------|---------------|
| 1 | HDFC Bank | 19 | ✅ Yes |
| 2 | Punjab National Bank | 19 | ✅ Yes |
| 3 | Axis Bank | 18 | ✅ Yes (PDF) |
| 4 | Union Bank of India | 18 | ✅ Yes |
| 5 | Bank of Baroda | 15 | ✅ Yes |
| 6 | Federal Bank | 14 | ✅ Yes |
| 7 | **IndusInd Bank** | **14** | ✅ **Yes (New)** |
| 8 | **IDFC FIRST Bank** | **13** | ✅ **Yes (New)** |
| 9 | Bank of Maharashtra | 12 | ✅ Yes |
| 10 | Central Bank of India | 12 | ✅ Yes |
| 11 | Canara Bank | 12 | ✅ Yes |
| 12 | Bandhan Bank | 11 | ❌ Generic |
| 13 | ICICI Bank | 10 | ✅ Yes (JSON API) |
| 14 | Shivalik Bank | 9 | ✅ Yes |
| 15 | State Bank of India | 8 | ✅ Yes |
| 16 | Kotak Mahindra Bank | 3 | ❌ Generic (Partial) |
| 17 | Indian Overseas Bank | 1 | ❌ Generic (Partial) |
| 18 | UCO Bank | 1 | ⚠️ Custom (Needs Fix) |

---

## Failed Extractions (12 Banks)

| # | Bank Name | Failure Reason |
|---|-----------|----------------|
| 1 | Bank of India | 403 Forbidden (Cloudflare protection) |
| 2 | Yes Bank | All parsing strategies failed |
| 3 | RBL Bank | All parsing strategies failed |
| 4 | DCB Bank | All parsing strategies failed |
| 5 | Karur Vysya Bank | All parsing strategies failed |
| 6 | City Union Bank | All parsing strategies failed |
| 7 | Jammu & Kashmir Bank | All parsing strategies failed |
| 8 | AU Small Finance Bank | 403 Forbidden (Website blocking) |
| 9 | Ujjivan Small Finance Bank | Connection failed (DNS error) |
| 10 | Suryoday Small Finance Bank | All parsing strategies failed |
| 11 | Utkarsh Small Finance Bank | All parsing strategies failed |
| 12 | Unity Small Finance Bank | All parsing strategies failed |

---

## Custom Parsers Implemented (15 Total)

### Working Custom Parsers (14)
1. **State Bank of India** - Multi-column rate table parser
2. **ICICI Bank** - JSON API parser
3. **Central Bank of India** - Specific table structure parser
4. **Federal Bank** - Multi-table parser (2 tables)
5. **Punjab National Bank** - Section-based parser
6. **HDFC Bank** - Structured table parser
7. **Bank of Maharashtra** - Staircase-pattern table parser
8. **Bank of Baroda** - Callable FD rates parser
9. **Canara Bank** - Annualized yield parser
10. **Axis Bank** - PDF parser (first in project)
11. **Union Bank of India** - Auto-calculated senior rates (+0.50%)
12. **Shivalik Bank** - Multi-table parser
13. **IndusInd Bank** - Annualized yield columns parser ✨ **NEW**
14. **IDFC FIRST Bank** - Standard table parser ✨ **NEW**

### Parsers Needing Attention (2)
1. **UCO Bank** - Returns 0 rates (needs debugging)
2. **AU Small Finance Bank** - Implemented but blocked by 403 error

---

## Key Achievements

### 1. IndusInd Bank Parser ✨
- **Status:** Successfully implemented
- **Extraction:** 14 rates (up from 1 rate)
- **Method:** Extracts annualized yield columns for deposits < ₹3 Cr
- **Columns Used:** 
  - Column 2: Annualized Yield (General)
  - Column 4: Annualized Yield (Senior Citizen)

### 2. IDFC FIRST Bank Parser ✨
- **Status:** Successfully implemented
- **Extraction:** 13 rates (up from 2 rates)
- **Method:** Standard table parser for deposits < ₹3 Crore
- **Columns Used:**
  - Column 1: General Rate
  - Column 2: Senior Citizen Rate

### 3. Rate Coverage
- **Total Rates:** 209 FD rate entries
- **Rate Range:** 3.25% to 7.71%
- **Tenure Coverage:** 7 days to 10 years
- **Customer Types:** Both general and senior citizens

---

## Output Files

All extraction results are saved in the `output/` directory:

1. **fd_rates_results.xlsx** - Complete rate data with 209 entries
   - Columns: Bank Name, Tenure, General Rate, Senior Citizen Rate, Duration (Days), etc.

2. **fd_rates_success.json** - Detailed success data for 18 banks

3. **fd_rates_failures.json** - Failure details for 12 banks

4. **extraction_summary.json** - Overall extraction statistics

---

## Technical Details

### Extraction Approach
- **Request Delay:** 1.0 second between banks
- **Max Retries:** 3 attempts per bank
- **Timeout:** 30 seconds per request
- **User Agent:** Mozilla/5.0 (standard browser simulation)

### Parser Types
- **HTML Table Parsers:** 12 banks
- **JSON API Parser:** 1 bank (ICICI)
- **PDF Parser:** 1 bank (Axis)
- **Generic Fallback:** 4 banks (partial success)

### Duration Parsing
- Successfully parsed: ~165 rates (79%)
- Failed to parse: ~44 rates (21%)
- Common issues: Non-standard tenure formats, special schemes

---

## Recommendations

### High Priority
1. **Fix UCO Bank Parser** - Currently returns 0 rates despite custom parser
2. **Investigate Kotak Bank** - Only 3 rates extracted (likely JavaScript-loaded content)
3. **Add Duration Patterns** - Improve parsing for special tenure formats

### Medium Priority
4. **Yes Bank** - Investigate page structure for custom parser
5. **RBL Bank** - Check if rates are in downloadable documents
6. **DCB Bank** - Examine page for dynamic content loading

### Low Priority
7. **Small Finance Banks** - Many have website access issues or non-standard formats
8. **Bank of India** - Blocked by Cloudflare (may need alternative approach)

---

## Conclusion

The FD rates extraction system successfully extracts comprehensive rate data from 60% of target banks, with **15 custom parsers** handling bank-specific page structures. The recent additions of **IndusInd Bank** and **IDFC FIRST Bank** parsers demonstrate the system's extensibility and effectiveness.

**Total Rate Coverage:** 209 FD rates across 18 major Indian banks, providing valuable data for deposits less than ₹3 Crore for both general and senior citizen customers.

---

*Report Generated: May 5, 2026*
