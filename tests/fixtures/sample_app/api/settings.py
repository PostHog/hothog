import config_sdk  # used at MODULE scope below -> not cleanly deferable (BLOCKED:modscope)

SETTING = config_sdk.load()
