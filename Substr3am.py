#!/usr/local/bin/python3

####################
#   Substr3am v1.0
#
#   @nexxai
#   github.com/nexxai/Substr3am
####################

import sys
import certstream
import tldextract
import re
import argparse

from sqlalchemy import create_engine, update
from declarative_sql import Subdomain, Base
from sqlalchemy.orm import sessionmaker

def print_callback(message, context):
    # Add any subdomains (or partial strings) you want to ignore here
    subdomains_to_ignore = [
        "www",
        "*",
        "azuregateway",
        "direwolf",
        "devshell-vm-",
        "device-local",
        "-local",
        "sni"
    ]

    subdomains_regex_to_ignore = [
        # 81d556ba781237c92f0c410f
        "[a-f0-9]{24}",                         
        
        # device1650096-3a628f22
        "device[a-f0-9]{7}-[a-f0-9]{8}",
        
        # e4751426-33f2-4239-9765-56b4cbcb505d
        "[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",

        #device-3e90cd1b-50dc-48f1-90ac-6389856ccb2e
        "device-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    ]

    if message['message_type'] == "heartbeat":
        return

    # These are the messages we care about
    if message['message_type'] == "certificate_update":
        # Some certificates have SAN addresses attached to them
        # so we want to know about all of them
        domains = message['data']['leaf_cert']['all_domains']

        # Get the domain name from the arguments
        domain_filter = parse_args().filter

        for domain in domains:
            # Use the tldextract library to break the domain into its parts
            extract = tldextract.extract(domain)

            # Determine the root domain by concatenating the chosen name ('microsoft') with the TLD/suffix ('com')
            computed_domain = extract.domain + '.' + extract.suffix

            # Only continue if one of the following are true:
            # - We are not filtering by domain at all
            # - We are filtering by domain and we have a match
            if domain_filter == None or (domain_filter != None and computed_domain in domain_filter):

                # Set the domain based on whether or not we're filtering 
                if domain_filter == None:
                    subdomain = extract.subdomain
                else:
                    subdomain = domain

                # Make sure there's actually something there
                if len(subdomain) > 0:

                    # Sometimes extract.subdomain gives us something like "www.testing.box"
                    # which is fine when we're filtering by domain by not when we're not
                    # so search for anything with a period in it
                    multi_level = subdomain.find(".")

                    # And then if it find something that has a period in it and we're not filtering...
                    if multi_level != -1 and domain_filter == None:
                        # Split it into two parts, the "www" and the "testing.box"...
                        subdomain_split = subdomain.split('.', 1)
                        # ...and we only care about the first entry
                        subdomain = subdomain_split[0]  

                    # This counter needs to stay at 0 if we're going to act on this entry
                    i = 0

                    # See if any of the subdomains_to_ignore are substrings of the one we're checking
                    # e.g. "devshell-vm" is a substring of "devshell-vm-0000-0000-00000000"
                    for search in subdomains_to_ignore:
                        # If it matches, increase the counter
                        if search in subdomain:
                            i += 1
                    
                    # See if any of the subdomains_regex_to_ignore are substrings of the one we're checking
                    for search in subdomains_regex_to_ignore:
                        # If it matches, increase the counter
                        if re.search(search, subdomain):
                            i += 1

                    # As long as none of the substrings or regexes match, continue on
                    if i == 0:
                        # Set up the connection to the sqlite db
                        engine = create_engine('sqlite:///subdomains.db')
                        Base.metadata.bind = engine
                        Session = sessionmaker()
                        Session.configure(bind=engine)
                        session = Session()

                        # Check to see if it already exists in the database...
                        subdomain_exists = session.query(Subdomain).filter_by(subdomain=subdomain).first()
                        
                        # It doesn't exist...
                        if not subdomain_exists:
                            # ...so create it
                            subdomain_new = Subdomain(subdomain=subdomain, count=1)
                            session.add(subdomain_new)
                            session.commit()

                            # Debug line
                            print("[+] " + subdomain)
                        
                        # It does exist
                        if subdomain_exists:
                            # Add one to the counter to track its popularity
                            counter = subdomain_exists.count + 1

                            # Add 1 to the counter
                            session.query(Subdomain).filter(Subdomain.id == subdomain_exists.id).\
                                update({'count': counter})
                            session.commit()

                            if (counter % 50 == 0):
                                print("[#] " + subdomain + " (seen " + str(counter) + " times)")
                        

def dump():
    # Set up the connection to the sqlite db
    engine = create_engine('sqlite:///subdomains.db')
    Base.metadata.bind = engine
    Session = sessionmaker()
    Session.configure(bind=engine)
    session = Session()

    # Get all the subdomains from the DB and sort them by popularity
    subdomains = session.execute("SELECT * FROM subdomains ORDER BY count DESC").fetchall()

    # Assuming there's anything in the list...
    if len(subdomains) > 0:
        # Open the file
        f = open("names.txt", "w")
        for subdomain in subdomains:
            # And write them
            f.write(subdomain.subdomain)
            f.write("\r\n")
        f.close()
    sys.exit('names.txt has been written')


def parse_args():
    # parse the arguments
    parser = argparse.ArgumentParser(epilog='\tExample: \r\npython ' + sys.argv[0] + " -d")
    parser.error = parser_error
    parser._optionals.title = "OPTIONS"
    parser.add_argument('-d', '--dump', help="Dump the list of collected subdomains to names.txt", action='store_true')
    parser.add_argument('-f', '--filter', help="A space-separated list of domain names to filter for (e.g. 'google.com' or 'tesco.co.uk tesco.com harrods.com'). BE PATIENT.", nargs='+')
    
    return parser.parse_args()

def parser_error(errmsg):
    banner()
    print("Usage: python " + sys.argv[0] + " [Options] use -h for help")
    print("Error: " + errmsg)
    sys.exit()

def main():
    # Actually connect to the certstream firehose, and listen for events
    certstream.listen_for_events(print_callback, url='wss://certstream.calidog.io/')

def interactive():
    args = parse_args()

    if args.dump:
        dump()

    banner()
    main()

def banner():
    G = '\033[92m'  # green
    Y = '\033[93m'  # yellow
    B = '\033[94m'  # blue
    R = '\033[91m'  # red
    W = '\033[0m'   # white

    print("""%s
  _________    ___.             __        ________                 
 /   _____/__ _\_ |__   _______/  |_______\_____  \_____    _____  
 \_____  \|  |  \ __ \ /  ___/\   __\_  __ \_(__  <\__  \  /     \ 
 /        \  |  / \_\ \\\\___ \  |  |  |  | \/       \/ __ \|  Y Y  \\
/_______  /____/|___  /____  > |__|  |__| /______  (____  /__|_|  /
        \/          \/     \/                    \/     \/      \/ %s%s

                # Coded By Justin Smith - @nexxai
    """ % (R, W, Y))

if __name__ == "__main__":
    interactive()
