def calculate_risk(probability: float) -> str:
    if probability < 30:
        return "HIGH"
    elif probability <= 50:
        return "MEDIUM"
    else:
        return "LOW"