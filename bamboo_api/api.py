"""
This module contains the BambooAPIClient, used for communicating with the
Bamboo server web service API.
"""

from bs4 import BeautifulSoup
import os
import requests


class BambooAPIClient(object):
    """
    Adapter for Bamboo's web service API.
    """
    # Default host is local
    DEFAULT_HOST = 'http://localhost'
    DEFAULT_PORT = 8085

    # Endpoints
    BUILD_SERVICE = '/rest/api/latest/result'
    PROJECT_SERVICE = 'rest/api/latest/project'
    DEPLOY_SERVICE = '/rest/api/latest/deploy/project'
    ENVIRONMENT_SERVICE = '/rest/api/latest/deploy/environment/{env_id}/results'
    PLAN_SERVICE = '/rest/api/latest/plan'
    QUEUE_SERVICE = '/rest/api/latest/queue'
    RESULT_SERVICE = '/rest/api/latest/result'
    SERVER_SERVICE = '/rest/api/latest/server'
    BFL_ACTION = '/build/label/viewBuildsForLabel.action'

    BRANCH_SERVICE = PLAN_SERVICE + '/{key}/branch'
    BRANCH_RESULT_SERVICE = RESULT_SERVICE + '/{key}/branch/{branch_name}'

    DELETE_ACTION = '/chain/admin/deleteChain!doDelete.action'

    def __init__(self, host=None, port=None, user=None, password=None, prefix=None):
        """
        Set connection and auth information (if user+password were provided).
        """
        self._host = host or self.DEFAULT_HOST
        self._port = port or self.DEFAULT_PORT
        self._prefix = prefix or ''
        self._session = requests.Session()
        if user and password:
            self._session.auth = (user, password)

    def _get_response(self, url, params=None):
        """
        Make the call to the service with the given queryset and whatever params
        were set initially (auth).
        """
        res = self._session.get(url, params=params or {}, headers={'Accept': 'application/json'})
        if res.status_code != 200:
            raise Exception(res.reason)
        return res

    def _post_response(self, url, params=None, data=None):
        """
        Post to the service with the given queryset and whatever params
        were set initially (auth).
        """
        res = self._session.post(url, params=params or {}, headers={'Accept': 'application/json'}, data=data or {})
        if res.status_code != 200:
            raise Exception(res.reason)
        return res

    def _put_response(self, url, params=None):
        """
        Put to the service with the given queryset and whatever params
        were set initially (auth).
        """
        res = self._session.put(url, params=params or {}, headers={'Accept': 'application/json'})
        if res.status_code != 200:
            raise Exception(res.reason)
        return res

    def _get_url(self, endpoint):
        """
        Get full url string for host, port and given endpoint.

        :param endpoint: path to service endpoint
        :return: full url to make request
        """
        return '{}:{}{}{}'.format(self._host, self._port, self._prefix, endpoint)

    def _build_expand(self, expand):
        valid_expands = set(['artifacts',
                             'comments',
                             'labels',
                             'jiraIssues',
                             'stages',
                             'stages.stage',
                             'stages.stage.results',
                             'stages.stage.results.result'])
        expands = map(lambda x: '.'.join(['results.result', x]),
                      set(expand) & valid_expands)
        return ','.join(expands)

    def get_builds_by_label(self, labels=None):
        """
        Get the master/branch builds in the Bamboo server via viewBuildsForLabel.action
        - No REST API for this: https://jira.atlassian.com/browse/BAM-18428
        - Scrape https://bamboo/build/label/viewBuildsForLabel.action?pageIndex=2&pageSize=50&labelName=foo
        Simple response API dict projectKey, planKey and buildKey

        :param labels: [str]
        :return: Generator
        """

        # Until BAM-18428, call the UI
        url = self._get_url(self.BFL_ACTION)
        qs = {}

        # Cannot search multiple labels in a single shot,
        # so iterate search - caller should de-dupe.
        for label in labels:
            qs['labelName'] = label

            # Cycle through paged results
            page_index = 1
            while 1:
                qs['pageIndex'] = page_index

                response = self._get_response(url, qs)

                # Build links are clustered in three inside a td containing a
                # span with build indicator icons.
                soup = BeautifulSoup(response.text, 'html.parser')
                for span in soup.find_all('span', {'class': ['aui-icon', 'aui-icon-small']}):
                    cell = span.find_parent('td')
                    if cell is not None and len(cell):
                        prj, plan, build = cell.find_all('a')[:3]

                        yield {'projectKey': os.path.basename(prj['href']),
                               'planKey': os.path.basename(plan['href']),
                               'buildKey': os.path.basename(build['href'])}

                # XXX rather than deconstruct the href, we advance our own
                # qs{pageIndex} until there are no more nextLinks
                page_index += 1
                nl = soup.find('a', {'class': ['nextLink']})
                if nl is None:
                    break

    def get_builds(self, plan_key=None, labels=None, expand=None, max_result=25):
        """
        Get the builds in the Bamboo server.

        :param plan_key: str
        :param labels: list str
        :param expand: list str
        :return: Generator
        """
        # Build starting qs params
        qs = {'max-result': max_result, 'start-index': 0}
        if expand:
            qs['expand'] = self._build_expand(expand)
        if labels:
            qs['label'] = ','.join(labels)

        # Get url
        if plan_key:
            # All builds for one plan
            url = '{}/{}'.format(self._get_url(self.BUILD_SERVICE), plan_key)
        else:
            # Latest build for all plans
            url = self._get_url(self.BUILD_SERVICE)

        # Cycle through paged results
        size = 1
        while size:
            # Get page, update page and size
            response = self._get_response(url, qs).json()
            results = response['results']
            size = results['size']

            # Check if start index was reset
            # Note: see https://github.com/liocuevas/python-bamboo-api/issues/6
            if results['start-index'] < qs['start-index']:
                # Not the page we wanted, abort
                break

            # Yield results
            for r in results['result']:
                yield r

            # Update paging info
            # Note: do this here to keep it current with yields
            qs['start-index'] += size

    def get_deployments(self, project_key=None):
        """
        Returns the list of deployment projects set up on the Bamboo server.
        :param project_key: str
        :return: Generator
        """
        url = "{}/{}".format(self._get_url(self.DEPLOY_SERVICE), project_key or 'all')
        response = self._get_response(url).json()
        for r in response:
            yield r

    def get_environment_results(self, environment_id, max_result=25):
        """
        Returns the list of environment results.
        :param environment_id: int
        :return: Generator
        """
        # Build starting qs params
        qs = {'max-result': max_result, 'start-index': 0}

        # Get url for results
        url = self._get_url(self.ENVIRONMENT_SERVICE.format(env_id=environment_id))

        # Cycle through paged results
        size = 1
        while qs['start-index'] < size:
            # Get page, update page size and yield results
            response = self._get_response(url, qs).json()
            size = response['size']
            for r in response['results']:
                yield r

            # Update paging info
            # Note: do this here to keep it current with yields
            qs['start-index'] += response['max-result']

    def get_plans(self, expand=None, max_result=25):
        """
        Return all the plans in a Bamboo server.

        :return: generator of plans
        """
        # Build starting qs params
        qs = {'max-result': max_result, 'start-index': 0}
        if expand:
            qs['expand'] = self._build_expand(expand)

        # Get url for results
        url = self._get_url(self.PLAN_SERVICE)

        # Cycle through paged results
        size = 1
        while qs['start-index'] < size:
            # Get page, update page size and yield plans
            response = self._get_response(url, qs).json()
            plans = response['plans']
            size = plans['size']
            for r in plans['plan']:
                yield r

            # Update paging info
            # Note: do this here to keep it current with yields
            qs['start-index'] += plans['max-result']

    def get_branches(self, plan_key, enabled_only=False, max_result=25):
        """
        Return all branches in a plan.

        :param plan_key: str
        :param enabled_only: bool

        :return: Generator
        """
        # Build qs params
        qs = {'max-result': max_result, 'start-index': 0}
        if enabled_only:
            qs['enabledOnly'] = 'true'

        # Get url for results
        url = self._get_url(self.BRANCH_SERVICE.format(key=plan_key))

        # Cycle through paged results
        size = 1
        while qs['start-index'] < size:
            # Get page, update page size and yield branches
            response = self._get_response(url, qs).json()
            branches = response['branches']
            size = branches['size']
            for r in branches['branch']:
                yield r

            # Update paging info
            # Note: do this here to keep it current with yields
            qs['start-index'] += branches['max-result']

    def delete_plan(self, build_key):
        """
        Delete a plan or plan branch with its key.

        :param build_key: str

        :return: dict Response
        """
        # Build qs params
        # qs = {}

        # Get url
        url = self._get_url(self.DELETE_ACTION)

        # Build Data Object
        data = {'buildKey': build_key}

        r = self._post_response(url, data=data)
        r.raise_for_status()

    def queue_build(self, plan_key, build_vars={}):
        """
        Queue a build for building

        :param plan_key: str
        :param build_vars: dict
        """
        url = "{}/{}".format(self._get_url(self.QUEUE_SERVICE), plan_key)

        # Custom builds
        qs = {}
        for k, v in build_vars.items():
            qs_k = 'bamboo.variable.{}'.format(k)
            qs[qs_k] = v

        return self._post_response(url, qs).json()

    def continue_build(self, plan_key, build_number, stage=None, executeAllStages=False, build_vars={}):
        """
        Queue a build for continuation

        :param plan_key: str
        :param build_vars: dict
        :param build_number: int
        :param stage: str
        """
        url = "{}/{}-{}".format(self._get_url(self.QUEUE_SERVICE), plan_key, build_number)

        # Custom builds
        qs = {}
        if executeAllStages:
            qs['executeAllStages'] = 'true'
        if stage:
            qs['stage'] = stage
        for k, v in build_vars.items():
            qs_k = 'bamboo.variable.{}'.format(k)
            qs[qs_k] = v

        return self._put_response(url, qs).json()

    def get_build_queue(self):
        """
        List all builds currently in the Queue
        """
        url = "{}".format(self._get_url(self.QUEUE_SERVICE))
        return self._get_response(url).json()

    def get_results(self, plan_key=None, build_number=None, expand=None, max_result=25):
        """
        Returns a list of results for builds
        :param plan_key: str
        :return: Generator
        """
        # Build qs params
        qs = {'max-result': max_result, 'start-index': 0}
        if expand:
            qs['expand'] = self._build_expand(expand)

        if build_number is not None and plan_key is not None:
            plan_key = plan_key + '-' + build_number
        url = "{}/{}".format(self._get_url(self.RESULT_SERVICE), plan_key or 'all')

        # Cycle through paged results
        size = 1
        while qs['start-index'] < size:
            # Get page, update page size and yield branches
            response = self._get_response(url, qs).json()
            results = response['results']
            size = results['size']
            for r in results['result']:
                yield r

            # Update paging info
            # Note: do this here to keep it current with yields
            qs['start-index'] += results['max-result']

    def get_branch_results(self, plan_key, branch_name=None, expand=None, favorite=False,
                           labels=None, issue_keys=None, include_all_states=False,
                           continuable=False, build_state=None, max_result=25):
        """
        Returns a list of results for plan branch builds

        :param plan_key: str
        :param branch_name: str
        :param expand: list str
        :param favorite: bool
        :param labels: list
        :param issue_keys: list
        :param include_all_states: bool
        :param continuable: bool
        :param build_state: str

        :return: Generator
        """
        # Build qs params
        qs = {'max-result': max_result, 'start-index': 0}
        if expand:
            qs['expand'] = self._build_expand(expand)
        if favorite:
            qs['favorite'] = True
        if labels:
            qs['label'] = ','.join(labels)
        if issue_keys:
            qs['issueKey'] = ','.join(issue_keys)
        if include_all_states:
            qs['includeAllStates'] = True
        if continuable:
            qs['continuable'] = True
        if build_state:
            valid_build_states = ('Successful', 'Failed', 'Unknown')
            if build_state not in valid_build_states:
                raise ValueError('Incorrect value for \'build_state\'. Valid values include: %s',
                                 ','.join(valid_build_states))
            qs['build_state'] = build_state

        # Get url for results
        url = self._get_url(self.BRANCH_RESULT_SERVICE.format(key=plan_key, branch_name=branch_name))

        # Cycle through paged results
        size = 1
        while qs['start-index'] < size:
            # Get page, update page size and yield branches
            response = self._get_response(url, qs).json()
            results = response['results']
            size = results['size']
            for r in results['result']:
                yield r

            # Update paging info
            # Note: do this here to keep it current with yields
            qs['start-index'] += results['max-result']

    def get_projects(self):
        """
        List all projects
        """
        url = "{}".format(self._get_url(self.PROJECT_SERVICE))
        response = self._get_response(url).json()
        return response

    def pause(self):
        """
        Pause server
        """
        url = "{}/{}".format(self._get_url(self.SERVER_SERVICE), "pause")
        return self._post_response(url).json()

    def resume(self):
        """
        Resume server
        """
        url = "{}/{}".format(self._get_url(self.SERVER_SERVICE), "resume")
        return self._post_response(url).json()

    def get_branch_variables(self, url, variable_number):
        response = self._session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        for span in soup.find_all('td',
                                  {'class': ['variable-value-container']}):
            variable_value = span.find_all('span')[variable_number]
            return variable_value.string
