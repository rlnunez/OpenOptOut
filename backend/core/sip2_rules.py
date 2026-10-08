"""
SIP2 Patron Eligibility Rule Engine.
Evaluates ILS patron responses against administrator-configured eligibility criteria:
1. Library / Branch (AQ, AF, AO) - contains, in list, not in list, equals
2. Age (PA, PB) - calculated from birthdate; supports greater than, less than, between
3. Patron Profile Type (PC) - equals, in list, not in list
4. Custom SIP2 2-letter fields
5. Boolean combinators:
   - "all" (AND): All conditions must be met
   - "any" (OR): At least one condition must be met
   - Complex nested rule groups: An "all" group containing "any" subgroups, or vice versa.
"""

import json
import re
from datetime import datetime, date
from typing import Optional, List, Dict, Tuple, Any, Union


def parse_patron_birthdate(raw_dob: str, date_format: Optional[str] = "auto") -> Optional[date]:
    """
    Parse a birthdate string from SIP2 response field PA or PB.
    Handles standard and configured ILS date formats:
    - 'auto' (default: checks YYYYMMDD, ISO, then falls back to MM/DD/YYYY unless day > 12)
    - 'MM/DD/YYYY' (US: Month first)
    - 'DD/MM/YYYY' (International / UK / EU: Day first)
    - 'YYYYMMDD' (3M SIP2 standard 8-digit numeric)
    - 'YYYY-MM-DD' (ISO 8601)
    - 'YYYY/MM/DD'
    """
    if not raw_dob or not str(raw_dob).strip():
        return None

    clean = str(raw_dob).strip()
    fmt = str(date_format or "auto").strip().upper()

    # 1. Standard 3M SIP2: YYYYMMDD (8 digits)
    if re.fullmatch(r"\d{8}", clean):
        try:
            return datetime.strptime(clean, "%Y%m%d").date()
        except ValueError:
            pass

    # 2. ISO: YYYY-MM-DD or YYYY/MM/DD
    m_iso = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", clean)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            return date(y, m, d)
        except ValueError:
            pass

    # 3. Delimited day & month: p1/p2/YYYY or p1-p2-YYYY
    m_delim = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", clean)
    if m_delim:
        p1, p2, y = int(m_delim.group(1)), int(m_delim.group(2)), int(m_delim.group(3))

        # Check if format specifies Day first (DD/MM/YYYY)
        prefers_dd = fmt in ("DD/MM/YYYY", "DD-MM-YYYY", "DD.MM.YYYY", "INTERNATIONAL", "EU", "UK") or fmt.startswith("DD")
        # Check if format specifies Month first (MM/DD/YYYY)
        prefers_mm = fmt in ("MM/DD/YYYY", "MM-DD-YYYY", "MM.DD.YYYY", "US") or fmt.startswith("MM")

        if prefers_dd:
            # Day first: p1=day, p2=month
            try:
                return date(y, p2, p1)
            except ValueError:
                try:
                    return date(y, p1, p2)
                except ValueError:
                    pass
        elif prefers_mm:
            # Month first: p1=month, p2=day
            try:
                return date(y, p1, p2)
            except ValueError:
                try:
                    return date(y, p2, p1)
                except ValueError:
                    pass
        else:
            # 'auto': If p1 > 12, it must be day -> DD/MM/YYYY
            if p1 > 12:
                try:
                    return date(y, p2, p1)
                except ValueError:
                    pass
            # Default to MM/DD/YYYY
            try:
                return date(y, p1, p2)
            except ValueError:
                try:
                    return date(y, p2, p1)
                except ValueError:
                    pass

    return None


def calculate_patron_age(
    raw_dob: Any,
    reference_date: Optional[date] = None,
    date_format: Optional[str] = "auto"
) -> Optional[int]:
    """
    Calculate real-time age in full years from a birthdate string or integer.
    If raw_dob is already a numeric age (e.g. "25" or 25), returns it directly.
    """
    if raw_dob is None:
        return None

    # If it's already an integer or a 1-3 digit age string
    if isinstance(raw_dob, (int, float)):
        return int(raw_dob)
    clean = str(raw_dob).strip()
    if re.fullmatch(r"\d{1,3}", clean) and int(clean) <= 130:
        return int(clean)

    dob = parse_patron_birthdate(clean, date_format=date_format)
    if not dob:
        return None

    today = reference_date or date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return max(0, age)


def _normalize_string_list(val: Any) -> List[str]:
    """Normalize input (list, comma-separated string, space-separated) into cleaned lowercase strings."""
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        items = val
    else:
        # Split on commas first; if no commas, split on whitespace if multiple words
        s = str(val).strip()
        if "," in s:
            items = s.split(",")
        else:
            items = [s]
    out = []
    for item in items:
        cleaned = str(item).strip().lower()
        if cleaned:
            out.append(cleaned)
    return out


def _resolve_profile_field(field_name: str, raw_profile: Dict[str, Any]) -> Tuple[Optional[str], Optional[Any]]:
    """
    Resolve semantic field names to SIP2 field codes and extract raw value.
    Returns (resolved_code, raw_value).
    """
    profile = raw_profile or {}
    fn = field_name.strip().lower()

    if fn in ("library", "branch", "location"):
        # Check AQ (branch code), AF (screen msg/branch), AO (institution id)
        for code in ("AQ", "AF", "AO"):
            if code in profile and str(profile[code]).strip():
                return code, str(profile[code]).strip()
        # Fallback to mapped branch_code on profile object if present
        if "branch_code" in profile:
            return "branch_code", str(profile["branch_code"]).strip()
        return "AQ", ""

    if fn in ("age", "birthdate", "dob"):
        # Check PA, PB
        for code in ("PA", "PB"):
            if code in profile and str(profile[code]).strip():
                return code, profile[code]
        if "age" in profile:
            return "age", profile["age"]
        return "PA", ""

    if fn in ("profile", "profile_type", "user_profile", "patron_type", "category"):
        # Check PC (patron profile/type), PI (patron identifier)
        for code in ("PC", "PI", "PZ"):
            if code in profile and str(profile[code]).strip():
                return code, str(profile[code]).strip()
        return "PC", ""

    # Custom 2-letter SIP2 code (case-insensitive)
    code_upper = field_name.strip().upper()
    return code_upper, profile.get(code_upper, "")


def evaluate_condition(
    condition: Dict[str, Any],
    raw_profile: Dict[str, Any],
    reference_date: Optional[date] = None,
    date_format: Optional[str] = "auto"
) -> Tuple[bool, str]:
    """
    Evaluate a single condition against a patron's SIP2 profile fields.
    Returns (passed: bool, reason: str).
    """
    field_name = str(condition.get("field", "")).strip()
    operator = str(condition.get("operator", "in")).strip().lower()
    target_value = condition.get("value")

    if not field_name:
        return True, "Empty field condition ignored"

    code, raw_val = _resolve_profile_field(field_name, raw_profile)

    # ── Age-specific evaluations ──
    if field_name.lower() in ("age", "birthdate", "dob"):
        eff_fmt = condition.get("date_format") or date_format or "auto"
        patron_age = calculate_patron_age(raw_val, reference_date=reference_date, date_format=eff_fmt)
        if patron_age is None:
            return False, f"Patron birthdate/age is missing or invalid in SIP2 field '{code}'"

        if operator in ("between", "range"):
            # Expect target_value to be [min, max] or "min-max" or "min and max"
            min_age, max_age = None, None
            if isinstance(target_value, (list, tuple)) and len(target_value) >= 2:
                try:
                    min_age, max_age = int(target_value[0]), int(target_value[1])
                except (ValueError, TypeError):
                    pass
            elif isinstance(target_value, str):
                nums = re.findall(r"\d+", target_value)
                if len(nums) >= 2:
                    min_age, max_age = int(nums[0]), int(nums[1])
                elif len(nums) == 1:
                    min_age, max_age = int(nums[0]), 999

            if min_age is None or max_age is None:
                return False, f"Invalid age range specified: {target_value}"

            if min_age <= patron_age <= max_age:
                return True, f"Patron age ({patron_age}) is between {min_age} and {max_age}"
            return False, f"Patron age ({patron_age}) is not between {min_age} and {max_age}"

        try:
            val_num = int(re.search(r"\d+", str(target_value)).group(0)) if target_value is not None else 0
        except (AttributeError, ValueError):
            val_num = 0

        if operator in ("greater_than", ">", "gt"):
            passed = patron_age > val_num
            return passed, f"Patron age ({patron_age}) > {val_num}: {passed}"
        elif operator in ("greater_than_or_equal", ">=", "gte", "min"):
            passed = patron_age >= val_num
            return passed, f"Patron age ({patron_age}) >= {val_num}: {passed}"
        elif operator in ("less_than", "<", "lt"):
            passed = patron_age < val_num
            return passed, f"Patron age ({patron_age}) < {val_num}: {passed}"
        elif operator in ("less_than_or_equal", "<=", "lte", "max"):
            passed = patron_age <= val_num
            return passed, f"Patron age ({patron_age}) <= {val_num}: {passed}"
        elif operator in ("equals", "==", "eq"):
            passed = patron_age == val_num
            return passed, f"Patron age ({patron_age}) == {val_num}: {passed}"
        elif operator in ("not_equals", "!=", "neq"):
            passed = patron_age != val_num
            return passed, f"Patron age ({patron_age}) != {val_num}: {passed}"

    # ── Text and list evaluations (Library, Profile Type, Custom) ──
    str_val = str(raw_val or "").strip().lower()
    targets = _normalize_string_list(target_value)

    if operator in ("in", "contains", "any_of", "one_of"):
        if not targets:
            return True, "No target list configured"
        # Check if str_val matches any target or if target is substring
        matched = any(t == str_val or t in str_val for t in targets)
        return matched, f"'{str_val}' in {targets}: {matched}"

    elif operator in ("not_in", "not_contains", "none_of", "is_not"):
        if not targets:
            return True, "No target list configured"
        matched = any(t == str_val or t in str_val for t in targets)
        return not matched, f"'{str_val}' not in {targets}: {not matched}"

    elif operator in ("equals", "==", "eq", "is"):
        first_target = targets[0] if targets else ""
        passed = (str_val == first_target)
        return passed, f"'{str_val}' equals '{first_target}': {passed}"

    elif operator in ("not_equals", "!=", "neq", "is_not_equal"):
        first_target = targets[0] if targets else ""
        passed = (str_val != first_target)
        return passed, f"'{str_val}' not equals '{first_target}': {passed}"

    # Unknown operator: pass by default
    return True, f"Unsupported operator '{operator}' bypassed"


def evaluate_sip2_eligibility(
    rules_cfg: Optional[Union[Dict[str, Any], str]],
    raw_profile: Dict[str, Any],
    reference_date: Optional[date] = None,
    date_format: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Recursively evaluate full SIP2 eligibility rule tree.
    Supports nested groups and 'all' / 'any' logic combinators.
    Returns (is_eligible: bool, detail_reason: str).
    """
    if not rules_cfg:
        return True, "No SIP2 eligibility rules configured"

    if isinstance(rules_cfg, str):
        try:
            cfg = json.loads(rules_cfg)
        except Exception:
            return True, "Malformed eligibility rules JSON ignored"
    elif isinstance(rules_cfg, dict):
        cfg = rules_cfg
    else:
        return True, "Invalid rules format"

    # If rules block is disabled
    if cfg.get("enabled") is False:
        return True, "SIP2 eligibility rules are disabled"

    eff_date_format = date_format or cfg.get("date_format") or "auto"
    mode = str(cfg.get("mode", "all")).lower().strip()
    rule_items = cfg.get("rules", [])
    if not rule_items:
        return True, "Empty rules list"

    results = []
    for item in rule_items:
        if not isinstance(item, dict):
            continue

        # Nested rule group (contains its own 'rules' array)
        if "rules" in item:
            sub_passed, sub_msg = evaluate_sip2_eligibility(
                item, raw_profile, reference_date=reference_date, date_format=eff_date_format
            )
            results.append((sub_passed, f"Group [{item.get('mode', 'all')}]: {sub_msg}"))
        else:
            passed, msg = evaluate_condition(
                item, raw_profile, reference_date=reference_date, date_format=eff_date_format
            )
            results.append((passed, msg))

    if not results:
        return True, "No valid rules evaluated"

    if mode == "any":
        # OR: at least one must pass
        any_passed = any(r[0] for r in results)
        if any_passed:
            passing_reasons = [r[1] for r in results if r[0]]
            return True, f"Eligible (passed condition: {passing_reasons[0]})"
        else:
            reasons = "; ".join(r[1] for r in results)
            return False, f"Patron does not meet any of the required criteria ({reasons})"
    else:
        # AND: all must pass
        all_passed = all(r[0] for r in results)
        if all_passed:
            return True, "Eligible (all conditions satisfied)"
        else:
            failing_reasons = [r[1] for r in results if not r[0]]
            return False, f"Patron failed eligibility requirement: {failing_reasons[0]}"


def validate_sip2_rules(cfg: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate structure of SIP2 eligibility rules configuration.
    """
    if cfg is None:
        return True, None
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except Exception as e:
            return False, f"Invalid JSON in eligibility rules: {e}"

    if not isinstance(cfg, dict):
        return False, "Eligibility rules must be a JSON dictionary"

    mode = cfg.get("mode", "all")
    if str(mode).lower() not in ("all", "any"):
        return False, "Rule group mode must be 'all' or 'any'"

    rules = cfg.get("rules", [])
    if not isinstance(rules, list):
        return False, "'rules' must be a list of rule conditions"

    for r in rules:
        if not isinstance(r, dict):
            return False, "Each rule must be a dictionary"
        if "rules" in r:
            valid, err = validate_sip2_rules(r)
            if not valid:
                return False, err
        else:
            if "field" not in r:
                return False, "Rule condition is missing required 'field' attribute"
            op = str(r.get("operator", "in")).lower()
            valid_ops = (
                "in", "contains", "any_of", "one_of",
                "not_in", "not_contains", "none_of", "is_not",
                "equals", "==", "eq", "not_equals", "!=", "neq",
                "between", "range",
                "greater_than", ">", "gt", "greater_than_or_equal", ">=", "gte", "min",
                "less_than", "<", "lt", "less_than_or_equal", "<=", "lte", "max"
            )
            if op not in valid_ops:
                return False, f"Unsupported operator '{op}' in rule for field '{r.get('field')}'"

    return True, None
