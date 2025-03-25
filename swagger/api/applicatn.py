from dgda.api.applicant_helper.profile import *
from frappe import whitelist

@whitelist(methods=["GET"])
def get_all(**kwargs) -> dict:
    return GetAll().run(kwargs)


@whitelist(methods=["GET"])
def get(id) -> dict:
    return Get().run(id=id)


@whitelist(methods=["POST","PUT"])
def edit(**kwargs) -> dict:
    return Edit().run(kwargs)

@whitelist(methods=["POST","PUT"])
def submit(**kwargs) -> dict:
    return Submit().run(kwargs)