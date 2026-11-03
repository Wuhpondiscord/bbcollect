"""Live public program documents; preserve policy text and native reward tables."""
import json
import re
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit

from collector import (CollectionError, CSRFParser, DIRECTORY, get_json, session, utcnow)

H1_DETAIL = """
query PublicDetails($handle: String!, $after: String, $rewardsAfter: String) {
  team(handle: $handle) {
    handle name policy scope_description currency
    minimum_bounty minimum_bounty_table_value maximum_bounty_table_value
    policy_setting {
      policy has_structured_policy last_policy_change_at
      structured_policy { brand_promise preferences process safe_harbor scope url }
    }
    declarative_policy {
      introduction disclosure_declaration has_open_scope
      protected_by_gold_standard_safe_harbor protected_by_ai_safe_harbor
      exemplary_standards_exclusions
      scope_exclusions { category details }
      platform_standards_exclusions { platform_standard justification }
    }
    bounty_table {
      description use_range updated_at
      bounty_table_rows(first: 100, after: $rewardsAfter) {
        nodes { name description low low_minimum medium medium_minimum
                high high_minimum critical critical_minimum }
        pageInfo { hasNextPage endCursor }
      }
    }
    structured_scopes(first: 100, after: $after, archived: false) {
      nodes { asset_identifier asset_type eligible_for_bounty eligible_for_submission
              instruction max_severity confidentiality_requirement
              integrity_requirement availability_requirement }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def numeric_range(ranges):
    minimums = [r.get("min") for r in ranges if isinstance(r.get("min"), (int, float))]
    maximums = [r.get("max") for r in ranges if isinstance(r.get("max"), (int, float))]
    return min(minimums) if minimums else None, max(maximums) if maximums else None


def hackerone(handle):
    with session() as client:
        response = client.get(DIRECTORY, timeout=(10, 30))
        response.raise_for_status()
        parser = CSRFParser()
        parser.feed(response.text)
        if not parser.token:
            raise CollectionError("No public session")
        client.headers.update({"X-CSRF-Token": parser.token, "Referer": DIRECTORY})
        assets, rows, after, rewards_after = [], [], None, None
        seen_scopes, seen_rewards = set(), set()
        scope_done = rewards_done = False
        for _ in range(100):
            payload = get_json(client.post("https://hackerone.com/graphql", json={
                "query": H1_DETAIL, "variables": {"handle": handle, "after": after,
                                                  "rewardsAfter": rewards_after}}, timeout=(10, 30)))
            if payload.get("errors"):
                raise CollectionError("Public detail query rejected")
            team = payload.get("data", {}).get("team")
            if not isinstance(team, dict):
                raise CollectionError("Public program not found")
            connections = [(team.get("structured_scopes"), assets, seen_scopes, scope_done),
                           ((team.get("bounty_table") or {}).get("bounty_table_rows"), rows,
                            seen_rewards, rewards_done)]
            cursors, done = [], []
            for connection, output, seen, finished in connections:
                if finished or connection is None:
                    cursors.append(None)
                    done.append(True)
                    continue
                if not isinstance(connection.get("nodes"), list):
                    raise CollectionError("Unexpected detail schema")
                output.extend(connection["nodes"])
                page = connection.get("pageInfo", {})
                cursor = page.get("endCursor")
                more = page.get("hasNextPage", False)
                if more and (not cursor or cursor in seen):
                    raise CollectionError("Invalid detail pagination")
                seen.add(cursor)
                cursors.append(cursor)
                done.append(not more)
            after, rewards_after = cursors
            scope_done, rewards_done = done
            if all(done):
                break
            time.sleep(0.15)
        else:
            raise CollectionError("Detail pagination exceeded limit")
    table = team.get("bounty_table")
    if table:
        table["bounty_table_rows"] = rows
    return {"min_bounty": team.get("minimum_bounty_table_value") if team.get("minimum_bounty_table_value") is not None else team.get("minimum_bounty"),
            "max_bounty": team.get("maximum_bounty_table_value"), "currency": team.get("currency"),
            "reward_table": table,
            "rules": {"policy": team.get("policy"), "scope_description": team.get("scope_description"),
                      "policy_setting": team.get("policy_setting"), "declarative_policy": team.get("declarative_policy")},
            "targets": {"in_scope": [a for a in assets if a.get("eligible_for_submission") is True],
                        "out_of_scope": [a for a in assets if a.get("eligible_for_submission") is not True]},
            "source_url": f"https://hackerone.com/{handle}",
            "source_updated_at": (team.get("policy_setting") or {}).get("last_policy_change_at")}


class BriefParser(HTMLParser):
    endpoint = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("data-react-class") == "ResearcherEngagementBrief":
            endpoints = json.loads(attrs.get("data-api-endpoints", "{}"))
            self.endpoint = endpoints.get("engagementBriefApi", {}).get("getBriefVersionDocument")


def bugcrowd(handle):
    url = f"https://bugcrowd.com/engagements/{handle}"
    with session() as client:
        response = client.get(url, timeout=(10, 30))
        response.raise_for_status()
        parser = BriefParser()
        parser.feed(response.text)
        endpoint = parser.endpoint
        # Only follow public same-origin brief paths, never arbitrary page URLs.
        if not endpoint or not endpoint.startswith(f"/engagements/{handle}/changelog/") or urlsplit(endpoint).netloc:
            raise CollectionError("Public brief endpoint not found")
        document_url = "https://bugcrowd.com" + endpoint + ".json"
        document = get_json(client.get(document_url, timeout=(10, 30)))
    data = document["data"]
    brief, groups = data["brief"], data["scope"]
    ranges = [r for group in groups if group.get("inScope") is True
              for r in (group.get("rewardRangeData") or {}).values() if isinstance(r, dict)]
    minimum, maximum = numeric_range(ranges)
    targets = {"in_scope": [], "out_of_scope": []}
    for group in groups:
        key = "in_scope" if group.get("inScope") is True else "out_of_scope"
        for asset in group.get("targets", []):
            targets[key].append({**asset, "group_name": group.get("name"),
                                 "group_description": group.get("descriptionHtml") or group.get("description"),
                                 "reward_range": group.get("rewardRangeData")})
    return {"min_bounty": minimum, "max_bounty": maximum,
            "currency": brief.get("currency"), "reward_table": [
                {"group": g.get("name"), "in_scope": g.get("inScope"),
                 "ranges": g.get("rewardRangeData"), "raw": g.get("rewardRange")} for g in groups],
            "rules": {"format": "html", "description": brief.get("description"),
                      "targets_overview": brief.get("targetsOverview"),
                      "additional_information": brief.get("additionalInformation"),
                      "safe_harbor": brief.get("safeHarborStatus"),
                      "coordinated_disclosure": document.get("coordinatedDisclosure"),
                      "vrt_scope_rules": document.get("vrtScopeRules"),
                      "resources": data.get("resources"), "scope_groups": groups},
            "targets": targets, "source_url": document_url,
            "source_updated_at": document.get("publishedAt")}


def latest(versions):
    return max(versions or [], key=lambda v: v.get("createdAt") or 0, default={}).get("content")


def intigriti(program):
    # Derive company and slug only from the trusted dataset URL.
    parts = urlsplit(program["url"])
    match = re.fullmatch(r"/programs/([A-Za-z0-9_.%-]+)/([A-Za-z0-9_.%-]+)/detail/?", parts.path)
    if parts.hostname != "www.intigriti.com" or not match:
        raise CollectionError("Unexpected public program URL")
    url = "https://app.intigriti.com/api/core/public/programs/" + "/".join(match.groups())
    with session() as client:
        document = get_json(client.get(url, timeout=(10, 30)))
    # Do not collect a program whose public visibility has changed.
    if document.get("confidentialityLevel") != 4:
        raise CollectionError("Program is no longer public")
    groups = (latest(document.get("assetsCollection")) or {}).get("assetsAndGroups", [])
    assets = []
    def flatten(items, parents=()):
        for item in items:
            if "assets" in item:
                flatten(item["assets"], parents + ({k: v for k, v in item.items() if k != "assets"},))
            else:
                assets.append({**item, "groups": list(parents)})
    flatten(groups)
    table = latest(document.get("bountyTables"))
    ranges = [{"min": (r.get("minBounty") or {}).get("value"),
               "max": (r.get("maxBounty") or {}).get("value")}
              for row in (table or {}).get("bountyRows", []) for r in row.get("bountyRanges", [])]
    minimum, maximum = numeric_range(ranges)
    return {"min_bounty": minimum, "max_bounty": maximum, "currency": (table or {}).get("currency"),
            "reward_table": table, "targets": {
                "in_scope": [a for a in assets if a.get("bountyTierId") != 5],
                "out_of_scope": [a for a in assets if a.get("bountyTierId") == 5]},
            "rules": {"description": document.get("description"), **{key: latest(document.get(key))
                       for key in ("inScopes", "outOfScopes", "faqs", "severityAssessments", "rulesOfEngagements")}},
            "source_url": url, "source_updated_at": None}


def yeswehack(handle):
    url = f"https://api.yeswehack.com/programs/{handle}"
    with session() as client:
        document = get_json(client.get(url, timeout=(10, 30)))
    if document.get("public") is not True:
        raise CollectionError("Program is no longer public")
    if not isinstance(document.get("scopes"), list):
        raise CollectionError("Unexpected public program schema")
    return {"min_bounty": document.get("bounty_reward_min"), "max_bounty": document.get("bounty_reward_max"),
            "currency": (document.get("business_unit") or {}).get("currency"),
            "reward_table": {k: v for k, v in document.items() if k.startswith("reward_grid_")},
            "targets": {"in_scope": document["scopes"], "out_of_scope": document.get("out_of_scope", [])},
            "rules": {key: document.get(key) for key in (
                "rules", "rules_html", "qualifying_vulnerability", "non_qualifying_vulnerability",
                "account_access", "account_access_html", "user_agent", "attachments", "supported_languages",
                "vpn_active", "systemic_issue_rule_enabled", "systemic_issue_rule_grid",
                "leakage_rule_enabled", "leakage_rule_grid_in_scope", "leakage_rule_grid_out_of_scope")},
            "source_url": url, "source_updated_at": document.get("last_update_at")}


def live_details(platform, handle, program=None):
    if platform == "hackerone":
        result = hackerone(handle)
    elif platform == "bugcrowd":
        result = bugcrowd(handle)
    elif platform == "intigriti":
        result = intigriti(program)
    else:
        result = yeswehack(handle)
    return {**result, "ok": True, "partial": False, "mode": "live",
            "fetched_at": utcnow(), "platform": platform, "handle": handle,
            "field_status": {"targets": "available", "rules": "available" if result.get("rules") else "not_published",
                             "min_bounty": "available" if result.get("min_bounty") is not None else "not_published",
                             "max_bounty": "available" if result.get("max_bounty") is not None else "not_published"}}
