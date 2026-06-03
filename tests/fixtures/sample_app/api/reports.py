import heavy_sdk  # second importer of heavy_sdk; both funnel through sample_app.api


def monthly():
    return heavy_sdk.report()
