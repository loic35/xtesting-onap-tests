# xtesting-onap-tests
Python framework to automate the instantiation of VNF using ONAP

## Changes in Code
  - Handle Service Versions
  - Handle multiple VF_modules (VNFCs) within a VNF
  - Add rollback capability 
  - Minor changes of log levels for some messages
  - Improve robustness (exception handling of some cases)
  - Get Output parameters of the Base module Stack to inject them in Incremental modules
  - Handle the initial_count to create the correct number of instances at startup
  
## Changes in YAML input file format:
- Add possibility to use a random string on some parameters (to avoid collision when multiple instantiations)
- Service Version & multiple VF_modules per VNF

### Previous format (still supported):
```
ServiceName:
    subscription_type: ServiceSubscriptionName
    VNF_Name 0:
      vnf_parameters: [
      ...
      ]
```

### New format:
```
ServiceName:
    subscription_type: ServiceSubscriptionName
    service_version: 'x.y'  # 1.0 used when missing
    add_random_to_parameters: [
        <parameterX from vnf_parameters list>,
        ...
    ]
    
    VNF_Name 0:
      module-0:
        vnf_parameters: [
        ...
        ]
      module-1:
        vnf_parameters: [
        ...
        ]
```