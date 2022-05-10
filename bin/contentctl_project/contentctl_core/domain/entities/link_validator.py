from lib2to3.pytree import Base
import re
from tracemalloc import start
from unittest.mock import DEFAULT
from pydantic import BaseModel, validator, root_validator,Field
from typing import Union, Callable
import requests
import urllib3, urllib3.exceptions
import time
import abc

DEFAULT_USER_AGENT_STRING = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.41 Safari/537.36"
class LinkStats(BaseModel):
    #Static Values
    method: Callable = requests.get
    allowed_http_codes: list[int] = [200] 
    access_count: int = 1 #when constructor is called, it has been accessed once!
    timeout_seconds: int = 15
    allow_redirects: bool = True
    headers: dict = {"User-Agent": DEFAULT_USER_AGENT_STRING}
    verify_ssl: bool = False
    if verify_ssl is False:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    #Values generated at runtime.
    #We need to assign these some default values to get the 
    #validation working since ComputedField has not yet been 
    #introduced to Pydantic
    reference: str
    referencing_files: set[str]
    redirect: Union[str,None] = None
    status_code: int = 0
    valid: bool = False
    resolution_time: float = 0 
    
    
    def is_link_valid(self, referencing_file:str)->bool:
        self.access_count += 1
        self.referencing_files.add(referencing_file)
        return self.valid
    
    @root_validator
    def check_reference(cls, values):
        start_time = time.time()
        #Get out all the fields names to make them easier to reference
        method = values['method']
        reference = values['reference']
        timeout_seconds = values['timeout_seconds']
        headers = values['headers']
        allow_redirects = values['allow_redirects']
        verify_ssl = values['verify_ssl']
        allowed_http_codes = values['allowed_http_codes']
        if not (reference.startswith("http://") or reference.startswith("https://")):
            raise(ValueError(f"Reference {reference} does not begin with http(s). Only http(s) references are supported"))
        
        try:
            get = method(reference, timeout=timeout_seconds, 
                            headers = headers, 
                            allow_redirects=allow_redirects, verify=verify_ssl)
            resolution_time = time.time() - start_time
            values['status_code'] = get.status_code
            values['resolution_time'] = resolution_time
            if reference != get.url:
                values['redirect'] = get.url
            else:
                values['redirect'] = None #None is also already the default

            #Returns the updated values and sets them for the object
            if get.status_code in allowed_http_codes:
                values['valid'] = True
            else:
                #print(f"Unacceptable HTTP Status Code {get.status_code} received for {reference}")
                values['valid'] = False
            return values    

        except Exception as e:
            resolution_time = time.time() - start_time
            #print(f"Reference {reference} was not reachable after {resolution_time:.2f} seconds")
            values['status_code'] = 0
            values['valid'] = False
            values['redirect'] = None
            values['resolution_time'] = resolution_time
            return values


class LinkValidator(abc.ABC):
    cache: dict[str,LinkStats] = {}
    uncached_checks: int = 0
    total_checks: int = 0
    #cache: dict[str,LinkStats] = {}

    
    @staticmethod
    def validate_reference(reference: str, referencing_file:str, raise_exception_if_failure: bool = False) -> bool:
        LinkValidator.total_checks += 1
        if reference not in LinkValidator.cache:
            LinkValidator.uncached_checks += 1
            LinkValidator.cache[reference] = LinkStats(reference=reference, referencing_files = set([referencing_file]))
        result = LinkValidator.cache[reference].is_link_valid(referencing_file)

        #print(f"Total Checks: {LinkValidator.total_checks}, Percent Cached: {100*(1 - LinkValidator.uncached_checks / LinkValidator.total_checks):.2f}")

        if result is True:
            return True
        elif raise_exception_if_failure is True:
            raise(Exception(f"Reference Link Failed: {reference}"))
        else:
            return False
    @staticmethod
    def print_link_validation_errors():
        for k in LinkValidator.cache.keys():
            if LinkValidator.cache[k].valid is False:
                print(f"Link {k} invalid with HTTP Status Code [{LinkValidator.cache[k].status_code}] and referenced by the following files:")
                for ref in LinkValidator.cache[k].referencing_files:
                    print(f"\t* {ref}")
