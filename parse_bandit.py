import json
with open('b:/DevHacks/DevHacks/bandit_report.json') as f:
    data = json.load(f)
for issue in data.get('results', []):
    if issue.get('issue_severity') == 'HIGH' or issue.get('issue_confidence') == 'HIGH':
        print(f"{issue['filename']}:{issue['line_number']} - {issue['issue_text']} (Sev: {issue['issue_severity']}, Conf: {issue['issue_confidence']})")
