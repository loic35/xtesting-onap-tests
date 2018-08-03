#!/usr/bin/python
#
# This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
#  pylint: disable=missing-docstring
import logging
import os
import time

from keystoneauth1 import loading
from keystoneauth1 import session
from heatclient import client

import onap_tests.utils.utils as onap_test_utils


class StackChecker(object):
    """
        Class used to check is the Stack does exist in openstack
        And if the status is complete
    """

    LOG_LEVEL = onap_test_utils.get_config("general.log.log_level")

    logging.basicConfig()
    __logger = logging.getLogger(__name__)
    logging.getLogger().setLevel(LOG_LEVEL)

    def __init__(self, **kwargs):
        """Initialize MRF object."""
        super(StackChecker, self).__init__()

        # get param from env variables
        auth_url = self.get("OS_AUTH_URL")
        username = self.get("OS_USERNAME")
        password = self.get("OS_PASSWORD")
        project_id = self.get("OS_PROJECT_ID")
        project_name = self.get("OS_PROJECT_NAME")
        user_domain_name = self.get("OS_USER_DOMAIN_NAME")
        loader = loading.get_plugin_loader('password')
        try:
            auth = loader.load_from_options(auth_url=auth_url,
                                            username=username,
                                            password=password,
                                            project_id=project_id,
                                            project_name=project_name,
                                            user_domain_name=user_domain_name)
            sess = session.Session(auth=auth)
            self.heat = client.Client('1', session=sess)
            self._OS_vars_set = True
        except Exception:  # pylint: disable=broad-except
            self.__logger.error("Env variables not found, impossible to get"
                                " keystone client")
            self._OS_vars_set = False
            
        try:
            self.stack_name = kwargs["stack_name"]
        except KeyError:
            self.__logger.debug("No stack name provided at initialization")
            
        # Add a custom timeout
        self.STACK_LOOP_IN_SECS = 10    # Loop period
        
        if "stack_timeout" in kwargs:
            self.stack_timeout = kwargs["stack_timeout"]
        else:
            # default is 1mn timeout
            self.stack_timeout = 60
            
    def get_OS_vars_set(self):
        return self._OS_vars_set
        
    @staticmethod
    def get(env_var):
        """
        Get env variable
        """
        return os.environ.get(env_var)

    def check_stack_exists(self, stack_name):
        """
        Check if the stack exists in openstack
        """
        stack_found = False
        nb_try = 0
        nb_try_max = self.stack_timeout / self.STACK_LOOP_IN_SECS    # 5
        
        # ensure a loop at least
        if nb_try_max <= 0:
            nb_try_max = 1

        while stack_found is False and nb_try < nb_try_max:
            stack_list = list(self.heat.stacks.list())
            if stack_name in str(stack_list):
                self.__logger.info("Stack found")
                return True
            else:
                self.__logger.info("CheckStack [%s/%s] %s : Not Found yet...", nb_try, nb_try_max, stack_name)
            nb_try += 1
            time.sleep(self.STACK_LOOP_IN_SECS)
        return stack_found

    def check_stack_is_complete(self, stack_name):
        """
        Check the status of a stack
        """
        # we assume that the stack does exist
        stack_status_complete = False
        nb_try = 0
        nb_try_max = self.stack_timeout / self.STACK_LOOP_IN_SECS    # 5

        # ensure a loop at least
        if nb_try_max <= 0:
            nb_try_max = 1

        while stack_status_complete is False and nb_try < nb_try_max:
            stack_list = list(self.heat.stacks.list())
            found_stack = None
            for stack in stack_list:
                if hasattr(stack, 'stack_name'):
                    if stack_name in stack.stack_name:
                        found_stack = stack
                        break
                else:
                    self.__logger.error("CheckStack %s: invalid stack_list", stack_name)
                    return False

            if found_stack:
                if found_stack.stack_status == "CREATE_COMPLETE":
                    return True
                elif "FAILED" in found_stack.stack_status:
                    self.__logger.error("CheckStack : Failed Stack %s", stack_name)
                    return False
                else:
                    self.__logger.info("CheckStack [%s/%s] %s : Not COMPLETE yet...", nb_try, nb_try_max, stack_name)
            else:
                self.__logger.info("CheckStack [%s/%s] %s : Not Found yet...", nb_try, nb_try_max, stack_name)
                
            nb_try += 1
            time.sleep(self.STACK_LOOP_IN_SECS)
        if found_stack is None:
            self.__logger.info("CheckStack : Stack %s does not exist!", stack_name)
            
        return stack_status_complete

    def get_stack_outputs(self, stack_name):
        """
        Get the Outputs/values and the status of a stack
        """
        dict_outputs = {}
        sStatus = None
        
        stacks = list(self.heat.stacks.list(filters={'name':stack_name}))
        if len(stacks) == 1:
            self.__logger.debug("stack: %s", stacks[0])
            sStatus = stacks[0].stack_status
            stack_id = stacks[0].id

            lOutput = self.heat.stacks.output_list( stack_id )['outputs']
            self.__logger.debug("stack_outputs: %s", lOutput) 
            for output in lOutput:
                output_name = output['output_key']
                value = self.heat.stacks.output_show( stack_id, output_name)['output']['output_value']
                self.__logger.debug("%s ==> %s", output_name, value)
                dict_outputs[output_name] = value
            
        else:
            self.__logger.error("get_stack_outputs: %s stack(s) found instead of 1", len(stacks))
            
        return (dict_outputs, sStatus)

