import config_sdk  # used at MODULE scope below -> not cleanly deferrable (BLOCKED:modscope)

SETTING = config_sdk.load()
