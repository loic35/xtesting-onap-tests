# Content


This module allows the instantiation of NS, VNF & VNFC using ONAP internal APIs (A&AI, SO and SDNC).
It gets the structure of the service from its TOSCA template YAML file, Preload parameters to override (with a preload) from a custom Config file (YAML).
Then Preload is done with SDNC component, Service, VNF & VNFC (modules) created with SO APIs, and the A&AI is updated.

## Features Added
- handle multiples ONAP VNFC (*modules*) per VNF
