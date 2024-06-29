Introduction
============

Overview of Automation-v2
--------------------------

Automation-V2 is a versatile framework for executing automated integration
tests. It uses reStructuredText (reST) for creating readable and multi-format
test artifacts, and Lisp for defining powerful, concise test steps. This
combination ensures accurate, maintainable, and extensible testing.

Automation-v2 is document focused. reStructuredText is fully embraced in 
all aspects of the framework. 

Background
----------

The MRTS project initially laid the groundwork for what would become
automation-v2. The history is not clear as the original developers have long
moved on from our company but it's name should give a clue that it was 
"version 2" of the automation framework. The framework was adopted on 
this program in 2017 initially by a single developer to help track the status
of new devlopement. Subsequently it has been adopted to as the unit test
solution for software development

Around the same time of program adoption the SIL project incorporated 
automation-v2. Eventually the framework was refactor and essentially became
the SIL architecture and implementation. The name automation-v2 was dropped 
and now SIL and automation-v2 can sort of be seen as marginally synonymous.
Eventhough automation-v2 and SIL split nearly many years ago. 

Incorporation into the SIL Project
----------------------------------

The SIL (Software Integration and Lifecycle) project incorporated Automation-V2
as a core component. Despite the integration, the architecture of Automation-V2
has remained consistent, with the SIL project focusing on enhancing the
framework through the creation of plugins and additional tooling, such as
editor support.

Core Usage and RVT Files
------------------------

Automation-V2 is predominantly used to run `.rvt` files, which are typically
integration level 2 black box test scripts. RVT stands for Requirement
Verification Test, and these scripts play a crucial role in verifying that
software requirements are met through automated testing. While the framework
supports other formats, `.rvt` files have become synonymous with Automation-V2.

This document aims to provide a comprehensive overview of Automation-V2,
covering its motivation, key features, technical architecture, and practical
usage guidelines. Whether you are a developer looking to extend the framework
or a tester writing and running scripts, this guide will equip you with the
knowledge needed to effectively utilize Automation-V2.
