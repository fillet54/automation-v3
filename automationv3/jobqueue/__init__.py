'''Distributed Test Runner

The runner packeage is a vesatile package designed to streamline the management 
and execution of automated tests in a distributed computing environment. It 
serves as the backbone for orchestrating test runs, distributing tasks to 
worker nodes, collecting results, and facilitating the efficient sharing 
of file system trees essential for testing processes.

-------------
Key Features
-------------

Queue Management
----------------
The module provides a robust queue management system that allows users to 
enqueue tests effortlessly along with the filesystem of the set of binaries 
that are the target of the tests. 

Distributed Execution
---------------------
Leveraging a worker pool, the module efficiently dispatches queued tests 
to available worker nodes. This distribution enhances parallel processing 
capabilities, significantly reducing test execution times.

Result Collection
-----------------
The runner collects and consolidates test results from worker nodes, offering 
a centralized view of the overall test run status. Comprehensive logs and 
reports are generated for easy analysis.

Filesystem Tree Storage
-----------------------
The runner is designed to allow a user to test work-in-progress code by 
allowing a user to seamlessly upload their current filesystem tree when a 
test is queued. The approach involves implementing and distributing a 
'git object store' formatted tree and objects to the a centralized runner 
node which can distribute to workers.

'''

from .views import jobqueue
