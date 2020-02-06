from bamboo_api import BambooAPIClient

bamboo_url = "<BAMBOO_URL>"
bamboo_user = "<BAMBOO_USER>"
bamboo_password = "<BAMBOO_PASSWORD>"
specific_branch = "develop"

bamboo = BambooAPIClient(user=bamboo_user, password=bamboo_password, host=bamboo_url,
                         port=443)

for plan in bamboo.get_plans():
    plan_key = plan['planKey']['key']
    for branch in bamboo.get_branches(plan_key=plan_key):
        if branch['shortName'] == specific_branch:
            url = branch['key']
            first_variable = bamboo.get_branch_variables(
                bamboo_url + '/branch/admin/config/editChainBranchVariables.action?buildKey=' + url, 0)
            if first_variable != str('0'):
                print(
                    "NAME= {} BRANCH KEY= {} --> firstVariable={}".format(branch['name'], branch['key'],
                                                                          first_variable))
