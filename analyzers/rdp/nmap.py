import copy
import re

try:
  # https://github.com/tiran/defusedxml
  import defusedxml.ElementTree
except ImportError:
  import sys
  sys.exit("this script requires the 'defusedxml' module.\nplease install it via 'pip3 install defusedxml'.")

from .. import Issue, AbstractParser
from . import SERVICE_SCHEMA

ENCRYPTION_LEVELS = {
  'Low': 'ENCRYPTION_LEVEL_LOW',
  'Client Compatible': 'ENCRYPTION_LEVEL_CLIENT',
  'High': 'ENCRYPTION_LEVEL_HIGH',
  'FIPS Compliant': 'ENCRYPTION_LEVEL_FIPS',
}

class Parser(AbstractParser):
  '''
  parse results of the Nmap RDP scan.

  $ nmap -sT -sU -Pn -sV -p {port} --script="banner,(rdp* or ssl*) and not (brute or broadcast or dos or external or fuzzer)" -oN "{result_file}.log" -oX "{result_file}.xml" {address}
  '''

  def __init__(self):
    super().__init__()

    self.name = 'nmap'
    self.file_type = 'xml'

  def parse_file(self, path):
    super().parse_file(path)

    '''
    https://nmap.org/book/nmap-dtd.html

    <nmaprun ...>
      <host ...>
        <address addr="192.168.42.1" addrtype="ipv4"/>
        <address addr="aa:bb:cc:dd:ee:ff" addrtype="mac" vendor="Vendor"/>
        <hostnames>
          <hostname name="example.com" type="PTR"/>
        </hostname>
        <ports>
          <port protocol="tcp" portid="3389">
            <state state="open" .../>
            <service name="ms-wbt-server" product="xrdp" method="probed" conf="10">...</service>
            <script id="rdp-enum-encryption" output="..." />
          </port>
          <port protocol="udp" portid="3389">
          ...
          </port>
        </ports>
    '''

    nmaprun_node = defusedxml.ElementTree.parse(path).getroot()

    for host_node in nmaprun_node.iter('host'):
      address = None

      for address_node in host_node.iter('address'):
        if address_node.get('addrtype') in ('ipv4', 'ipv6'):
          address = address_node.get('addr')
          break

      if address is None:
        continue

      for port_node in host_node.iter('port'):
        if port_node.find('state').get('state') != 'open':
          continue

        transport_protocol = port_node.get('protocol') # tcp/udp
        port = port_node.get('portid') # port number

        identifier = f"{address}:{port} ({transport_protocol})"

        if identifier in self.services:
          continue

        service = copy.deepcopy(SERVICE_SCHEMA)
        self.services[identifier] = service

        service['address'] = address
        service['transport_protocol'] = transport_protocol
        service['port'] = port

        service['info'] = []

        for script_node in port_node.iter('script'):
          script_ID = script_node.get('id')

          if script_ID == 'rdp-enum-encryption':
            self._parse_rdp_enum_encryption(script_node, service)
            continue

          if script_ID == 'rdp-ntlm-info':
            self._parse_rdp_ntlm_info(script_node, service)
            continue

          if 'rdp' in script_ID:
            self.__class__.logger.info(f"Nmap script scan result not parsed: '{script_ID}'")
            service['info'].append(f"Nmap script scan result not parsed: '{script_ID}'")
            #TODO: implement this

  def _parse_rdp_enum_encryption(self, script_node, service):
    # https://nmap.org/nsedoc/scripts/rdp-enum-encryption.html

    script_output = script_node.get('output')

    patterns_PROTOCOL = {
      'PROTOCOL_RDP': 'Native RDP: SUCCESS',
      'PROTOCOL_SSL': 'SSL: SUCCESS',
      'PROTOCOL_HYBRID': 'CredSSP (NLA): SUCCESS',
      'PROTOCOL_RDSTLS': 'RDSTLS: SUCCESS',
      'PROTOCOL_HYBRID_EX': 'CredSSP with Early User Auth: SUCCESS',
      #'PROTOCOL_RDSAAD': ,
    }

    for key, pattern in patterns_PROTOCOL.items():
      if pattern in script_output:
        service['protocols'].append(key)

    regex_ENCRYPTION_LEVEL = re.compile(r'RDP Encryption level: (Low|Client Compatible|High|FIPS Compliant)')
    m = regex_ENCRYPTION_LEVEL.search(script_output)
    if not m:
      service['encryption_level'] = 'ENCRYPTION_LEVEL_NONE'
    if m:
      service['encryption_level'] = ENCRYPTION_LEVELS[m.group(1)]

    pattern_NLA = 'CredSSP (NLA): SUCCESS'
    if pattern_NLA in script_output:
      service['NLA'] = True

  def _parse_rdp_ntlm_info(self, script_node, service):
    # https://nmap.org/nsedoc/scripts/rdp-ntlm-info.html
    # "Sending an incomplete CredSSP (NTLM) authentication request with null credentials will cause the remote service to respond with a NTLMSSP message disclosing information to include NetBIOS, DNS, and OS build version."

    for elem_node in script_node.iter('elem'):
      key = elem_node.get('key')
      value = elem_node.text

      service['misc'].append(f"NTLMSSP: `{key}={value}`")

      if key in ('DNS_Computer_Name', 'Product_Version'):
        service['issues'].append(
          Issue(
            "information disclosure",
            key = key,
            value = value
          )
        )
