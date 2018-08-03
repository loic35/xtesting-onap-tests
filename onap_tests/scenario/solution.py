#!/usr/bin/python
#
# This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# pylint: disable=missing-docstring
# pylint: disable=duplicate-code
import logging
import time
import sys

import onap_tests.components.aai as aai
import onap_tests.components.so as so
import onap_tests.components.sdnc as sdnc
import onap_tests.components.nbi as nbi
import onap_tests.utils.stack_checker as sc
import onap_tests.utils.utils as onap_utils

PROXY = onap_utils.get_config("general.proxy")


class Solution(object):
    """
    VNF: Class to automate the instantiation of a VNF
    It is assumed that the Design phase has been already done
    The yaml template is available and stored in the template directory
    TODO: automate the design phase
    """
    __logger = logging.getLogger("")   #logging.getLogger(__name__)

    def __init__(self, **kwargs):
        """Initialize Solution object."""
        super(Solution, self).__init__()
        
        #Check if Os_* vars are set
        if not self.check_env_vars():
           self.__logger.error("No OS_* environment variables detected : Exiting...")
           sys.exit(1)
           
        self.vnf_config = {}
        self.components = {}
        if "case" not in kwargs:
            # by convention is VNF is not precised we set mrf
            kwargs["case"] = "mrf"
        self.vnf_config["vnf"] = kwargs["case"]
        if "nbi" in kwargs:
            self.vnf_config["nbi"] = kwargs["nbi"]

        # can be useful to destroy resources, sdnc module name shall be given
        if "sdnc_vnf_name" in kwargs:
            self.vnf_config["sdnc_vnf_name"] = kwargs["sdnc_vnf_name"]
            # Random part = 6 last char of the the vnf name
            self.vnf_config["random_string"] = kwargs["sdnc_vnf_name"][-6:]
        else:
            self.vnf_config["random_string"] = (
                onap_utils.random_string_generator())
            self.vnf_config["sdnc_vnf_name"] = (
                onap_utils.get_config("onap.service.name") + "_" +
                kwargs["case"] + "_" + self.vnf_config["random_string"])

        LOG_LEVEL = onap_utils.get_config("general.log.log_level")
        if LOG_LEVEL == "DEBUG":
            self.__logger.info("DEBUG: Activated!")
            self.DebugActivated = True
        else:
            self.__logger.info("DEBUG: Not activated")
            self.DebugActivated = True
                
        vnf_list = list(onap_utils.get_template_param(
            self.vnf_config["vnf"],
            "topology_template.node_templates"))
        vf_module_list = list(onap_utils.get_template_param(
            self.vnf_config["vnf"],
            "topology_template.groups"))
        # Class attributes for instance, vnf and module VF
        self.service_infos = {}
        self.service_subscription_type = onap_utils.get_config(
            self.vnf_config["vnf"] + ".subscription_type")
        self.vnf_infos = {'list': vnf_list}
        self.module_infos = {'list': vf_module_list}
        
        # List of parameters of the preload to add a random key to
        self.parameters_random_addlist = onap_utils.get_config(
                    self.vnf_config["vnf"] + ".add_random_to_parameters")
                    
        # retrieve infos from the configuration files
        self.set_service_instance_var()
        self.set_vnf_var()
        self.set_module_var()
        self.set_onap_components()

    def set_service_instance_var(self):
        """
        set service instance variables from the config file
          Fix: Service version is not in the Tosca but in the Instantiation input file
        """
        self.vnf_config["vnf_name"] = onap_utils.get_template_param(
            self.vnf_config["vnf"], "metadata.name")
        self.vnf_config["invariant_uuid"] = onap_utils.get_template_param(
            self.vnf_config["vnf"], "metadata.invariantUUID")
        self.vnf_config["uuid"] = onap_utils.get_template_param(
            self.vnf_config["vnf"], "metadata.UUID")
        
        # Catch exception For backward compatibility with previous file format that does not contain any service_version
        try:
            self.vnf_config["version"] = onap_utils.get_config(
                self.vnf_config["vnf"] + ".service_version")
        except ValueError:
            # the default hardcoded version
            self.vnf_config["version"] = "1.0"
            self.__logger.info("No service_version in config file, using default %s", self.vnf_config["version"])

    def set_vnf_var(self):
        """
        set vnf variables from the config file
          Add the VNFs versions read from tosca file
        """
        for i, elt in enumerate(self.vnf_infos['list']):
            vnf_config = {}
            self.__logger.info("get VNF %s info", elt)
            vnf_config["vnf_customization_name"] = elt
            vnf_config["vnf_model_name"] = onap_utils.get_template_param(
                self.vnf_config["vnf"], "topology_template.node_templates." +
                vnf_config["vnf_customization_name"] + ".metadata.name")
            vnf_config["vnf_invariant_id"] = onap_utils.get_template_param(
                self.vnf_config["vnf"], "topology_template.node_templates." +
                vnf_config["vnf_customization_name"] +
                ".metadata.invariantUUID")
            vnf_config["vnf_version_id"] = onap_utils.get_template_param(
                self.vnf_config["vnf"], "topology_template.node_templates." +
                vnf_config["vnf_customization_name"] + ".metadata.UUID")
            vnf_config["vnf_customization_id"] = (
                onap_utils.get_template_param(
                    self.vnf_config["vnf"],
                    "topology_template.node_templates." +
                    vnf_config["vnf_customization_name"] +
                    ".metadata.customizationUUID"))
            # Fix: The index used to get the VF is not the same as the VNF index! (it works if only template contains 1 VNF with 1 VF)
            # => Moved to set_module_var in a VF specific context
            #vnf_config["vnf_type"] = list(onap_utils.get_template_param(
            #    self.vnf_config["vnf"], "topology_template.groups"))[i]
            vnf_config["vnf_generic_name"] = (
                self.vnf_config["vnf_name"] + "-service-instance-" +
                self.vnf_config["random_string"])
            vnf_config["vnf_generic_type"] = (
                self.vnf_config["vnf_name"] + "/" +
                vnf_config["vnf_customization_name"])
                
            # Get the VNF version from the tosca file
            vnf_config["vnf_version"] = onap_utils.get_template_param(
                self.vnf_config["vnf"], "topology_template.node_templates." + 
                vnf_config["vnf_customization_name"] + ".metadata.version")

            self.vnf_config[elt] = vnf_config

    def set_module_var(self):
        """
        set module variables from the config file
          Fix: a VNF can have multiple VF so we need to iterate also on VF modules to find matching VNFs they belong to
          Get modules versions from tosca groups
        """
        for elt in self.vnf_infos['list']:
            vf_config = {}

            # we cannot be sure that the modules are in the same order
            # than the vnf
            
            # iterate as long as some modules are found for the current VNF
            mod_index = 0
            vf_index = 0
            
            while vf_index >=0:
                # If no more module are found for current VNF, index returned is -1
                vf_index = onap_utils.get_vf_module_index(
                    self.module_infos['list'],
                    elt,
                    mod_index = mod_index)
                
                if vf_index == -1:
                    break
                
                module_name = "module-%s" % mod_index
                
                vnf_type = list(onap_utils.get_template_param(
                    self.vnf_config["vnf"],
                    "topology_template.groups"))[vf_index]

                # Move this item to the module layer of the context (to avoid beeing overwritten when multiple VF in the VNF!)
                #vf_config["sdnc_vnf_type"] = onap_utils.get_template_param(
                #    self.vnf_config["vnf"], "topology_template.groups." +
                #    vnf_type +
                #    ".metadata.vfModuleModelName")
                module_name = "module-%s" % mod_index
                vf_config[module_name] = {}
                vf_config[module_name]["sdnc_vnf_type"] = onap_utils.get_template_param(
                    self.vnf_config["vnf"], "topology_template.groups." +
                    vnf_type +
                    ".metadata.vfModuleModelName")
                self.__logger.info("get Module %s:%s info for VNF %s", module_name, vf_config[module_name]["sdnc_vnf_type"], elt)
                
                vnf_param = (self.vnf_config["vnf"] + "." +
                             str(elt) + ".vnf_parameters")
                
                # For backward compatibility: If there is only one VF module in the VNF, the yaml file is VNF.vnf_parameters
                # if multiple VF: VNF.<VF_module>.vnf_parameters
                    
                # vf_config["vnf_parameters"] = onap_utils.get_config(vnf_param)
                try:
                    vnf_vf_params = onap_utils.get_config(vnf_param)    # exception if not found (new format with module-x
                except ValueError:
                    # We look with the VF level in the yaml file
                    vnf_param = (self.vnf_config["vnf"] + "." +
                                 str(elt) + "." + module_name + ".vnf_parameters")
                    vnf_vf_params = onap_utils.get_config(vnf_param)

                # Add entry with the VNF.<module-x>.vnf_parameters
                vf_config[module_name]["vnf_parameters"] = vnf_vf_params
                    
                # Every field below the groups is related to a specific vf and shold be in the vf context (not the VNF context!)
                vf_config[module_name]["module_invariant_id"] = onap_utils.get_template_param(
                    self.vnf_config["vnf"], "topology_template.groups." +
                    vnf_type + ".metadata.vfModuleModelInvariantUUID")
                vf_config[module_name]["module_name_version_id"] = (
                    onap_utils.get_template_param(
                        self.vnf_config["vnf"], "topology_template.groups." +
                        vnf_type + ".metadata.vfModuleModelUUID"))
                vf_config[module_name]["module_customization_id"] = (
                    onap_utils.get_template_param(
                        self.vnf_config["vnf"], "topology_template.groups." +
                        vnf_type + ".metadata.vfModuleModelCustomizationUUID"))
                vf_config[module_name]["module_version_id"] = onap_utils.get_template_param(
                    self.vnf_config["vnf"], "topology_template.groups." +
                    vnf_type + ".metadata.vfModuleModelUUID")
                    
                # Keep the initial_count to identify how many instances of a module have to be instantiated at startup
                vf_config[module_name]["initial_count"] = onap_utils.get_template_param(
                    self.vnf_config["vnf"], "topology_template.groups." +
                    vnf_type + ".properties.initial_count")

                # Module version (& trailing '.0')
                vf_config[module_name]["module_version"] = onap_utils.get_template_param(
                    self.vnf_config["vnf"], "topology_template.groups." +
                    vnf_type + ".metadata.vfModuleModelVersion") + ".0"
                
                # Update the VNF Context with integrated VFs 
                self.vnf_config[elt].update(vf_config)
                
                # prepare index for next loop
                mod_index += 1
            
            # Keep Nb of VF_Module for this VNF
            self.vnf_config[elt]['vf_modules_count'] = mod_index
            
    def set_onap_components(self):
        """
        Set ONAP component objects
        """
        self.components["aai"] = aai.Aai(PROXY, self.__logger)
        
        # when Debug mode is activated,we won't destroy a Failed stack : Rollback is disabled        
        self.components["so"] = so.So(PROXY, self.__logger, disableRollback = self.DebugActivated)

        self.components["sdnc"] = sdnc.Sdnc(PROXY, self.__logger)

        # No need to init the NBI module is not used
        if "nbi" in self.vnf_config and self.vnf_config["nbi"]:
            self.components["nbi"] = nbi.Nbi(PROXY, self.__logger)

    def get_service_infos(self, service_type, service_name):
        """
        Get ServiceID and List of <VNF_Name,VNF_ID>
        """
        try:
            service_id = None
            serviceCtx = None
            vnf_infos_list = None
            bCont = True

            # Get Context of the service
            serviceCtx = self.components["aai"].get_service_instance(service_type, service_name)
            
            # Service not found
            if serviceCtx is None:
                bCont = False
            else:
                # on error
                if not serviceCtx: # True for {}
                    bCont = False
                    vnf_infos_list = [] # Error case
            
            if bCont:
                service_id = serviceCtx["service-instance-id"]
                
                vnf_infos_list = []

                # *** Service Context ***
                # if not set: Keep a service info context (needed when creating new VFs for this Service)
                # Note: this context should be exported in case the module is used with multiple services! 
                # (2 calls to this function for a different service update the current service active context)
                service_instance_info = {
                        "instance_id": service_id,
                        "request_info": None,   # To be updated if required by calling the SO
                        "service_payload": None}
                self.service_infos = service_instance_info                

                # Extract all VNFs of the Service
                vnf_idx = 0
                for relation in serviceCtx["relationship-list"]["relationship"]:
                    if relation["related-to"] == "generic-vnf":
                        vnf_infos = {}
                        # We assume here that the list contains only 1 element and the right one 
                        # Otherwise check property-key=="generic-vnf.vnf-name"
                        # and relationship-key=="generic-vnf.vnf-id"
                        vnf_infos["vnf_name"] = relation["related-to-property"][0]["property-value"]
                        vnf_infos["vnf_id"] = relation["relationship-data"][0]["relationship-value"]
                        vnf_infos_list.append(vnf_infos)
                        self.__logger.info("VNF found: %s", vnf_infos["vnf_name"])

                        # *** VNF context ***
                        vnf_related_instance = self.components["so"].get_vnf_related_instance(
                            self.service_infos["instance_id"],
                            self.vnf_config['invariant_uuid'],
                            self.vnf_config['uuid'],
                            self.vnf_config['version'])
            
                        vnf_info = {"vnf_id": vnf_infos["vnf_id"],
                                    "vnf_instance_name": vnf_infos["vnf_name"],
                                    "vnf_payload": None,            # To be updated if required
                                    "vnf_related_instance": vnf_related_instance}

                        elt = self.vnf_infos['list'][vnf_idx]
                        self.vnf_infos[elt] = vnf_info      
                        vnf_idx += 1
                        
        except Exception as err:  # pylint: disable=broad-except
            self.__logger.error("Unable to get infos for service: %s %s", service_name, str(err))
            
        return (service_id, vnf_infos_list)
            
    def instantiate(self):
        """
        Instantiate a VNF with ONAP
          * Create the service instance (SO)
          * Create the VNF instance (SO)
          * preload the VNF in the SDNC
             Fix: Preload each VF of a VNF
          * Create the VF module instance (SO)
             Fix: Create 0/1 VF instance according to initial_count
          * Result updated to contains a list of vf_info
        """
        self.__logger.info("Start the instantiation of the VNF")
        instance_info = {"instance_id": ""}
        vnf_info = {"vnf_id": ""}
        check_vnf = False
        vnf_ok = False

        module_info_list = []
        module_ref = {"instanceId": ""}
        module_ok = False

        instance_info = self.create_service_instance()
        service_ok = self.components["aai"].check_service_instance(
            self.vnf_config["vnf_name"],
            instance_info["instance_id"])
            
        if not service_ok:
            self.__logger.error("Unable to create service")
        else:
            # create VNF instance(s)
            for elt in self.vnf_infos['list']:
                vnf_info = self.create_vnf_instance(elt)
                self.__logger.info("Check vnf %s ....", elt)
                vnf_ok = True
                if not self.components["aai"].check_vnf_instance(
                        vnf_info["vnf_id"]):
                    vnf_ok = False
                    break
                #else:
                # # Fix: Preload is done at VF layer
                # # preload VNF(s) in SDNC
                #   self.preload(elt)
                #   time.sleep(10)

            if vnf_ok:
                # The global VNF check is currently Ok, We'll update it with VF checks
                check_vnf = True
                
                # create VF module(s)
                for elt in self.vnf_infos['list']:
                    module_info = {}
                    # The preload is now done at the VF layer (we can have different preload for each VF)
                    nb_vf = self.vnf_config[elt]['vf_modules_count']
                    mod_index = 0
                    
                    while mod_index < nb_vf:
                        module_name = "module-%s" % mod_index
                        mod_index += 1      # Next Module
                        
                        # Check if the VF has to be instantiated at startup
                        if self.vnf_config[elt][module_name]["initial_count"] < 1:
                            # no instance created for this VF
                            self.__logger.info("Module %s not created (initial_count condition)", module_name)
                            break
                        
                        (module_ok, module_info, check_vf) = self.instantiate_VF(elt, vnf_info["vnf_id"], module_name)
                        
                        # Set VNF check false as soon as a VF is false
                        check_vnf = check_vnf and check_vf
                        
                        # Update global VNF status
                        vnf_ok = vnf_ok and module_ok
                        
                        # Update the VF info list
                        module_info_list.append(module_info)
                                
        return {"status": vnf_ok,
                "instance_id": instance_info,
                "vnf_info": vnf_info,
                "module_info_list": module_info_list,
                "check_heat": check_vnf}

    def instantiate_VF(self, elt, vnf_id, module_name, input_dict={}):
        """
        Instantiate a VF(=module)
          input_dict = Optional dictionary containing input parameters for the preload
        """
        self.preload_VF(elt, module_name, input_dict=input_dict)
        time.sleep(10)
        
        check_vf = False
        module_info = self.create_module_instance(elt, module_name=module_name)
        module_ok = True
        module_ref = module_info['module_instance']
        if not self.components["aai"].check_module_instance(
                vnf_id,
                module_ref["requestReferences"]["instanceId"]):
            module_ok = False

        else:
            # check VNF using OpenStack directly
            check_vf = self.check_vnf(self.module_infos[elt]["module_instance_name"])
            if check_vf:
                self.__logger.info("Stack successfully checked")    
        return (module_ok, module_info, check_vf)
        
    def clean(self):
        """
        Clean VNF from ONAP

         Args:
            instance_id: The ID of the VNF service instance
            vnf_id: The ID of the VNF instance
            module_id: The ID of the VF module instance
        """
        instance_id = self.service_infos['instance_id']
        for elt in self.vnf_infos['list']:
            vnf_id = self.vnf_infos[elt]["vnf_id"]
            module_id = (self.module_infos[elt]["module_instance"]
                         ["requestReferences"]["instanceId"])
            self.clean_module(elt)
            if not self.components["aai"].check_module_cleaned(vnf_id,
                                                               module_id):
                return False
            else:
                self.clean_vnf(elt)
                if not self.components["aai"].check_vnf_cleaned(vnf_id):
                    return False
                else:
                    self.clean_instance(instance_id)
                    if self.components["aai"].check_service_instance_cleaned(
                            self.vnf_config["vnf_name"], instance_id):
                        self.__logger.debug("Instance still in AAI DB")
                    else:
                        return False
            time.sleep(10)
            self.clean_preload(elt)
        return True

    def create_service_instance(self):
        """
        Create service instance
        2 options to create the instance
          * with SO
          * with NBI
        """
        instance_id = None
        model_info = self.components["so"].get_service_model_info(
            self.vnf_config['invariant_uuid'], self.vnf_config['uuid'], self.vnf_config['version'])

        if self.vnf_config["nbi"]:
            self.__logger.info("1) Create Service instance from NBI")
            self.__logger.info("***********************************")
            request_info = self.components["nbi"].get_request_info()
            service_payload = (
                self.components["nbi"].get_nbi_service_order_payload())
            nbi_info = self.components["nbi"].create_service_order_nbi(
                service_payload)
            time.sleep(5)
            instance_id = (
                self.components["nbi"].get_service_instance_id_from_order(
                    nbi_info["id"]))
        else:
            self.__logger.info("1) Create Service instance in SO")
            self.__logger.info("********************************")
            request_info = self.components["so"].get_request_info(
                self.vnf_config["vnf"] + "-service-instance-" +
                self.vnf_config['random_string'])
            service_payload = self.components["so"].get_service_payload(
                self.vnf_config["vnf"],
                request_info,
                model_info)
            instance_id = self.components["so"].create_instance(
                service_payload)

        service_instance_info = {"instance_id": instance_id,
                                 "request_info": request_info,
                                 "service_payload": service_payload}
        self.__logger.debug("Service instance created: %s",
                           service_instance_info)
        self.service_infos = service_instance_info
        return service_instance_info

    def create_vnf_instance(self, elt):
        """
        Create VNF instance

        Args:
          * elt: the VNF
        """
        vnf_id = None
        self.__logger.info("2) Create VNF instance in SO")
        self.__logger.info("****************************")

        model_info = self.components["so"].get_vnf_model_info(
            self.vnf_config[elt]['vnf_invariant_id'],
            self.vnf_config[elt]['vnf_version'],
            self.vnf_config[elt]['vnf_version_id'],
            self.vnf_config[elt]['vnf_model_name'],
            self.vnf_config[elt]['vnf_customization_id'],
            self.vnf_config[elt]['vnf_customization_name'])

        vnf_related_instance = self.components["so"].get_vnf_related_instance(
            self.service_infos["instance_id"],
            self.vnf_config['invariant_uuid'],
            self.vnf_config['uuid'],
            self.vnf_config['version'])

        vnf_instance_name = (self.vnf_config["vnf"] + "-vnf-instance-" +
                             str(elt).replace(" ", "_") + ("_") +
                             self.vnf_config['random_string'])

        request_info = self.components["so"].get_request_info(
            vnf_instance_name)

        vnf_payload = self.components["so"].get_vnf_payload(
            self.vnf_config["vnf"],
            request_info,
            model_info,
            vnf_related_instance)
        # self.__logger.debug("VNF payload: %s", vnf_payload)
        vnf_id = self.components["so"].create_vnf(
            self.service_infos["instance_id"],
            vnf_payload)
        vnf_info = {"vnf_id": vnf_id,
                    "vnf_instance_name": vnf_instance_name,
                    "vnf_payload": vnf_payload,
                    "vnf_related_instance": vnf_related_instance}
        self.__logger.debug(">>>> SO vnf instance created %s", vnf_info)
        self.vnf_infos[elt] = vnf_info
        return vnf_info
    
    def preload_VF(self, elt, module_name="module-0", input_dict={}):
        """
        Preload VF in SDNC

        Args:
          * elt: the VF
          * Add some optional parameters:
              module-name: name of the module to preload
              input_dict: optionnal dictionnary of input to override 
              parameter format :
                {
                    'vnf-parameter-name': 'vProbe_name',
                    'vnf-parameter-value': 'vProbe'
                }
              
        """

        def add_random_string_to_parameters(random_string, parameters_random_addlist, vf_params_list):
            """
            A random string if used is added to some specific parameters
            """
            for idx, param in enumerate(vf_params_list):
                #if unicode(param['vnf-parameter-name']) == unicode(key):
                if param['vnf-parameter-name'] in parameters_random_addlist:
                    # Overwrite the value by adding a random_key
                    vf_params_list[idx]['vnf-parameter-value'] = vf_params_list[idx]['vnf-parameter-value'] + random_string
                    #print "Add_random to %s" % param
            return vf_params_list
        
        def add_preload_param( key, value, vf_params_list):
            """
            Overwrite a preload parameter or add it 
            """
            
            # Look for the new parameter in the existing ones
            bModified = False
            for idx, param in enumerate(vf_params_list):
                #if unicode(param['vnf-parameter-name']) == unicode(key):
                if param['vnf-parameter-name'] == key:
                    # Overwrite
                    vf_params_list[idx]['vnf-parameter-value'] = value
                    #print "Mod %s" % param
                    bModified = True
                    break
            if not bModified:
                # Add
                new_param = { 'vnf-parameter-name': key, 'vnf-parameter-value': value }
                vf_params_list.append(new_param)
                #print "Add %s" % new_param
                    
            # Merge modified list and new one
            return vf_params_list
                    
        vnf_preload_infos = {}
        self.__logger.info("3.1) Preload VF %s in SDNC", elt)
        self.__logger.info("*******************************")
        vnf_name = (self.vnf_config["vnf"] +
                        "-vnf-instance-" +
                        str(elt).replace(" ", "_") + "_" +
                        self.vnf_config['random_string'])
        vf_name = (self.vnf_config["vnf"] +
                        "-vfmodule-instance-" +
                        str(module_name) + "_" +
                        self.vnf_config['random_string'])
                        
        vnf_topology_identifier = {
            "generic-vnf-name": vnf_name,   # This is the name of the VNF, the same for all modules of the VNF
            "generic-vnf-type": (
                self.vnf_config[elt]['vnf_generic_type']),
            "service-type": self.service_infos["instance_id"],
            "vnf-name": vf_name, # Despite its name, This is the name related to the module => 1 stack per vf_module
            #Fix for multiple VF
            #"vnf-type": self.vnf_config[elt]['sdnc_vnf_type']}
            "vnf-type": self.vnf_config[elt][module_name]['sdnc_vnf_type']}

        # vnf_parameters of customized per VF (i.e. module_name)
        vf_parameters = self.vnf_config[elt][module_name]['vnf_parameters']

        # Is there any input parameters to override ? (i.e. for an incremental VF with output of the Base VF)
        if len(input_dict) > 0:
            # Some specific parameters to ignore because ONAP set them itself!
            # vnf_id, vnf_name, vf_module_id
            input_dict.pop('vnf_id', None)
            input_dict.pop('vnf_name', None)
            input_dict.pop('vf_module_id', None)
            
            self.__logger.debug( "Before=> %s", vf_parameters)
            for k in input_dict:
                # Avoid unicode string
                key = k.encode('ascii','ignore')
                if input_dict[k] is None:
                    value = None
                else:
                    value = input_dict[k].encode('ascii','ignore')
                vf_parameters = add_preload_param(key, value, vf_parameters)

            self.__logger.debug( "After=> %s", vf_parameters)        
            
        # Any parameters to add the random string to values ?       
        if len (self.parameters_random_addlist) >0:
            vf_parameters = add_random_string_to_parameters( self.vnf_config["random_string"], self.parameters_random_addlist, vf_parameters )        
        
        sdnc_payload = self.components["sdnc"].get_preload_payload(
            vf_parameters,
            vnf_topology_identifier)
        self.__logger.debug("SDNC preload payload %s", sdnc_payload)
        sdnc_preload = self.components["sdnc"].preload(sdnc_payload)
        self.__logger.debug("SDNC preload answer: %s", sdnc_preload)
        vnf_preload_infos[elt] = ({"sdnc_payload": sdnc_payload,
                                   "sdnc_preload": sdnc_preload})

        return vnf_preload_infos[elt]

    def create_module_instance(self, elt, module_name="module-0"):
        """
        Create module instance

        Args:
          * instance_info: dict including the instance_id, the request_info and
          the service payload
          * vnf_info: dict including the vnf_id, vnf_related_instance and the
          vnf payload
          * module_name : name of the VF (<module-x>) to match the preload name
        """
        module_info = {}
        self.__logger.info("4) Create MODULE %s instance in SO", elt)
        self.__logger.info("***************************************")

        module_model_info = self.components["so"].get_module_model_info(
            self.vnf_config[elt][module_name]['module_invariant_id'],
            self.vnf_config[elt][module_name]['module_version'],
            self.vnf_config[elt][module_name]['module_name_version_id'],
            self.vnf_config[elt][module_name]['sdnc_vnf_type'],
            self.vnf_config[elt][module_name]['module_customization_id'],
            self.vnf_config[elt][module_name]['module_version_id'])
        module_related_instance = (
            self.components["so"].get_module_related_instance(
                self.vnf_infos[elt]["vnf_id"],
                self.vnf_config[elt]['vnf_invariant_id'],
                self.vnf_config[elt]['vnf_version'],
                self.vnf_config[elt]['vnf_version_id'],
                self.vnf_config[elt]['vnf_model_name'],
                self.vnf_config[elt]['vnf_customization_id'],
                self.vnf_config[elt]['vnf_customization_name']))

        module_instance_name = (self.vnf_config["vnf"] +
                                "-vfmodule-instance-" +
                                #str(elt).replace(" ", "_") + "_" +
                                str(module_name) + "_" +
                                self.vnf_config['random_string'])

        request_info = self.components["so"].get_request_info(
            module_instance_name)

        module_payload = self.components["so"].get_module_payload(
            self.vnf_config["vnf"],
            request_info,
            module_model_info,
            self.vnf_infos[elt]["vnf_related_instance"],
            module_related_instance)

        self.__logger.debug("Module payload %s", module_payload)
        module_instance = self.components["so"].create_module(
            self.service_infos["instance_id"],
            self.vnf_infos[elt]["vnf_id"],
            module_payload)
        self.__logger.debug(">>>> Module instance created: %s", module_instance)
        self.__logger.info(">>>Module_ID = %s", module_instance["requestReferences"]["instanceId"])
        
        module_info = (
            {'module_instance': module_instance,
             'module_instance_name': module_instance_name,
             'module_payload': module_payload,
             'module_model_info': module_model_info,
             'module_related_instance': module_related_instance})
        self.__logger.debug("SO module vf(s) created: %s", module_info)
        self.module_infos[elt] = module_info
        return module_info

    def check_env_vars(self):
        bRes = False
        
        # Check if Openstack variables are defined
        my_stack_checker = sc.StackChecker(stack_timeout=10*60)
        if not my_stack_checker is None:
            bRes = my_stack_checker.get_OS_vars_set()
        
        return bRes

    def get_module_outputs(self, stack_name):
        """
        Get the output parameters of an existing stack and its status
        """
        status = None
        dRes = {}
        
        my_stack_checker = sc.StackChecker(stack_timeout=10)
        if not my_stack_checker is None:
            (dRes, status) = my_stack_checker.get_stack_outputs(stack_name)
               
        return (dRes, status)
        
    def check_vnf(self, stack_name, stack_timeout=10*60):
        """
        Check VNF stack has been properly started
        """
        check_vnf = False
        try:
            # LLL Add timeout 10 mn for vProbes(default is 1mn)
            my_stack_checker = sc.StackChecker(stack_timeout=stack_timeout)
            if my_stack_checker.check_stack_is_complete(stack_name):
                check_vnf = True
        except Exception as err:  # pylint: disable=broad-except
            self.__logger.error("Impossible to find the stack %s in OpenStack: %s",
                                stack_name, str(err) )
        return check_vnf

    def clean_instance(self, instance_id):
        """
        Clean VNF instance

        Args:
          * instance_id: The service instance of the VNF
        """
        self.__logger.info(" Clean Service Instance ")
        service_payload = self.components["so"].get_service_payload(
            self.vnf_config["vnf"],
            self.components["so"].get_request_info(
                self.vnf_config['sdnc_vnf_name']),
            self.components["so"].get_service_model_info(
                self.vnf_config['invariant_uuid'],
                self.vnf_config['uuid'],
                self.vnf_config['version']))
        self.components["so"].delete_instance(instance_id, service_payload)

    def clean_vnf(self, elt):
        """
        Clean  VNF

        Args:
          * instance_id: The service instance of the VNF
          * vnf_id:The VNF id of the VNF
        """
        self.__logger.info(" Clean vnf Instance %s ", elt)
        self.components["so"].delete_vnf(
            self.service_infos["instance_id"],
            self.vnf_infos[elt]["vnf_id"],
            self.vnf_infos[elt]["vnf_payload"])

    def clean_module(self, elt):
        """
        Clean VNF Module

        Args:
          * instance_id: The service instance id of the VNF
          * vnf_id:The VNF id of the VNF
          * module_id: the VF module id of the VNF
        """
        self.__logger.info(" Clean Module VF Instance %s ", elt)
        instance_id = self.service_infos["instance_id"]
        vnf_id = self.vnf_infos[elt]["vnf_id"]
        module_id = (self.module_infos[elt]["module_instance"]
                     ["requestReferences"]["instanceId"])
        module_payload = self.module_infos[elt]["module_payload"]
        self.components["so"].delete_module(
            module_payload,
            instance_id,
            vnf_id,
            module_id)

    def clean_preload(self, elt, module_name="module-0"):
        """
        Clean VNF SDNC preload
        """
        self.__logger.info(" Clean Preload of %s ", elt)
        # if 1 of the expected preload clean is FAIL we return False
        clean_preload = self.components["sdnc"].delete_preload(
            self.module_infos[elt]["module_instance_name"],
            #self.vnf_config[elt]["sdnc_vnf_type"])
            self.vnf_config[elt][module_name]["sdnc_vnf_type"])
        return clean_preload

    def clean_all_preload(self):
        """
        Clean VNF SDNC preload with the preload id
          Fix: Handle case when multiple VF in a VNF
        """
        self.__logger.info(" Clean Preload ")
        for elt in self.vnf_infos['list']:
          mod_index = 0
          while mod_index < self.vnf_config[elt].vf_modules_count:
            module_name = "module-%s" % mod_index
            mod_index += 1  # Next VF Module
            if not module_name in self.vnf_config[elt]:
              self.__logger.info(" Module %s not found!", module_name)
            else:
                clean_preload = self.components["sdnc"].delete_preload(
                    self.module_infos[elt]["module_instance_name"],
                    #self.vnf_config[elt]['sdnc_vnf_type'])
                    self.vnf_config[elt][module_name]['sdnc_vnf_type'])
        return clean_preload

    def get_info(self):
        """
        Get VNFs Info
        """
        self.__logger.info("Class to manage VNFs")
        self.__logger.info("VNF config: %s", self.vnf_config)
