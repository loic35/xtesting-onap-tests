#!/usr/bin/python
#
# This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
#  pylint: disable=missing-docstring

from difflib import SequenceMatcher

import logging
import random
import string
import os
import requests
import yaml

# Creation of a shared unique context : Singleton pattern ------------------------------------------
class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class Utils(object):
    __metaclass__ = Singleton
    # Context of the Singleton instance
    configFile = None
    templatePath = None
    logger = None
    
g_UtCtx = Utils()
#---------------------------------------------------------------------------------------------------
# Accessors of Context fields
def setConfigFile(configFile):
    g_UtCtx.configFile = configFile

def getConfigFile():
  return g_UtCtx.configFile

def setTemplatePath(path):
  g_UtCtx.templatePath = path

def getTemplatePath():
  return g_UtCtx.templatePath

#def getLogger():
#  if g_UtCtx.logger is None:
#    g_UtCtx.logger = logging.get_logger("")
#
#  return g_UtCtx.logger

# ----------------------------------------------------------
#
#               YAML UTILS
#
# -----------------------------------------------------------
def get_parameter_from_yaml(parameter, config_file):
    """
    Returns the value of a given parameter in file.yaml
    parameter must be given in string format with dots
    Example: general.openstack.image_name
    """
    with open(config_file) as my_file:
        file_yaml = yaml.safe_load(my_file)
    my_file.close()
    value = file_yaml

    # Ugly fix as workaround for the .. within the params in the yaml file
    ugly_param = parameter.replace("..", "##")
    for element in ugly_param.split("."):
        value = value.get(element.replace("##", ".."))
        if value is None:
            raise ValueError("The parameter %s is not defined" % parameter)
    return value


def get_config(parameter):
    """
    Get configuration parameter from yaml configuration file
    """
    # if no configfile set, we use the default local one 
    configFile = getConfigFile()
    if configFile is None:
        local_path = os.path.dirname(os.path.abspath(__file__))
        yaml_ = local_path.replace("utils", "onap-testing.yaml")
    else:
        yaml_ = configFile
    return get_parameter_from_yaml(parameter, yaml_)


def get_template_param(vnf_type, parameter):
    """
    Get VNF template
    """
    # if no TemplatePath set, we use the default local one 
    templatePath = getTemplatePath()
    
    if templatePath is None:
        local_path = os.path.dirname(os.path.abspath(__file__))
        if "ims" in vnf_type:
            template_path = "templates/service-ClearwaterVims-template.yml"
        elif "vfw" in vnf_type:
            template_path = "templates/service-VfwService-template.yml"
        else:
            template_path = "templates/service-VmrfService-template.yml"

        yaml_ = local_path.replace("utils",
                                   template_path)
    else:
        # The Template "service-<vnf_type>-template.yml" is searched in the Template Path
        # TODO: in fact the "vnf-type" parameter is the service name: to be renamed
        yaml_ = templatePath + "service-" + vnf_type + "-template" + ".yml"
        
    return get_parameter_from_yaml(parameter, yaml_)


# ----------------------------------------------------------
#
#               LOGGER UTILS
#
# -----------------------------------------------------------
def get_logger(module):
    """
    Get Logger
    """
    if g_UtCtx.logger is None:
        log_formatter = logging.Formatter("%(asctime)s [" +
                                          module +
                                          "] [%(levelname)-5.5s]  %(message)s")
        logger = logging.getLogger("")
        g_UtCtx.logger = logger
        log_file = get_config('general.log.log_file')
        log_level = get_config('general.log.log_level')

        file_handler = logging.FileHandler("{0}/{1}".format('.', log_file))
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)

        #console_handler = logging.StreamHandler()
        #console_handler.setFormatter(log_formatter)
        #logger.addHandler(console_handler)
        logger.setLevel(log_level)
  
    return g_UtCtx.logger

# ----------------------------------------------------------
#
#               Misc
#
# -----------------------------------------------------------
def random_string_generator(size=6,
                            chars=string.ascii_uppercase + string.digits):
    """
    Get a random String for VNF
    """
    return ''.join(random.choice(chars) for _ in range(size))


def get_vf_module_index(vnf_list, target, mod_index=0):
    """
    Find VF modules of the VNF
      Fix: Add a module index to handle cases wher a VNF has multiple VF
    """
    # To be able to trace here
    _logger = None  #getLogger()
    
    # until we understand how to match vnf & vf from the service template
    best_index = -1     # returns -1 if no matching
    best_index_proba = 0
    for i, elt in enumerate(vnf_list):
        
        # We must find the module-<mod_index> to continue with this name
        sMod = "module-%s" % mod_index
        if not sMod in elt.lower():
            if _logger: _logger.debug( "Ignoring module %s no match with %s/%s", elt, target, sMod )
        else:
            current_proba = SequenceMatcher(None,
                                            target.lower(),
                                            elt.lower()).ratio()
            if _logger: _logger.debug( "%s: %s::%s => CurrentProba=%s Best=%s", i, elt, target, current_proba, best_index_proba)
                
            if current_proba > best_index_proba:
                best_index = i
                best_index_proba = current_proba
    
    return best_index


# ----------------------------------------------------------
#
#               requests
#
# -----------------------------------------------------------
def get_simple_request(url, headers, proxy):
    try:
        response = requests.get(url, headers=headers,
                                proxies=proxy, verify=False)
        request_info = response.json()
    except Exception:  # pylint: disable=broad-except
        request_info = response.text
    return request_info

