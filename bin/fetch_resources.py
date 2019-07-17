#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from bs4 import BeautifulSoup
import requests
import json
import os.path
import yaml
import time
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper
from requests.exceptions import HTTPError
import logging
logging.basicConfig(level=logging.INFO)

MAX_PAGES_TO_PULL = 0


base_url = 'https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide'
starting_page = "aws-template-resource-type-ref.html"


top_level_resources = {}
resource_subtypes = {}


def get_resource_pages():
    root_url = f'{base_url}/{starting_page}'
    logging.info(json.dumps({
        "method": "get_resource_pages",
        "root_url": root_url
    }, indent=4, sort_keys=True))

    tree = get_page(root_url)
    for li in tree.find_all('li'):
        resource_link = li.find('a')
        top_level_resources[resource_link.string] = resource_link.get('href')

    logging.debug(json.dumps({
        "top_level_resources": top_level_resources
    }, indent=4, sort_keys=True))


def get_resource_subtypes():
    logging.info(json.dumps({
        "method": "get_resource_subtypes"
    }, indent=4, sort_keys=True))

    i = 0
    for resource_name, resource_page in top_level_resources.items():
        temp_subtypes = []
        logging.debug(json.dumps({
            "resource_name": resource_name,
            "resource_page": resource_page
        }, indent=4, sort_keys=True))

        tree = get_page(f'{base_url}/{resource_page}')

        for li in tree.find_all('li', attrs={"class": "listitem"}):
            subtype_link = li.find('a')
            temp_subtypes.append({"name": subtype_link.string, "url": subtype_link.get('href')})

            logging.debug(json.dumps({
                "temp_subtypes": temp_subtypes
            }, indent=4, sort_keys=True))

        resource_subtypes[resource_name] = temp_subtypes
        logging.debug(json.dumps({
            "resource_subtypes": resource_subtypes
        }, indent=4, sort_keys=True))

        i += 1
        if MAX_PAGES_TO_PULL != 0 and i >= MAX_PAGES_TO_PULL:
            logging.warning('Reached Limit of pulled resources. Stopping process.')
            break


def text_cleanup(in_text):
    p1 = in_text.splitlines()
    p2 = [i.strip() for i in p1]
    return ' '.join(p2)

def collect_subtypes_for_resource():
    logging.info(json.dumps({
        "method": "collect_subtypes_for_resource"
    }, indent=4, sort_keys=True))

    for resource_name, resource_details in resource_subtypes.items():
        final_output = {}
        logging.debug(json.dumps({
            "resource_name": resource_name,
            "resource_details": resource_details
        }, indent=4, sort_keys=True))

        subtypes = []
        for resource_type in resource_details:
            logging.debug(json.dumps({
                "resource_type": resource_type
            }, indent=4, sort_keys=True))

            subtype_content = get_page(f'{base_url}/{resource_type.get("url")}')

            subtype_description = subtype_content.find('div', id="main-col-body").find('p').get_text()

            subtype_yaml_head = resource_type.get('name').split('::')[-1] + ':\n  '
            subtype_yaml_string = subtype_content.find('code', class_="yaml").get_text()
            subtype_yaml_out = subtype_yaml_head + subtype_yaml_string.replace('\n', '\n  ')

            subtype_yaml = yaml.load(subtype_yaml_out, Loader=Loader)
            logging.warning(subtype_yaml)

            try:
                subtype_variables = subtype_content.find('div', class_='variablelist').find('dl')
            except AttributeError as aErr:
                continue

            terms = []
            definitions = []
            subtype_properties = []
            for dts in subtype_variables.find_all('dt'):
                terms.append(dts.get_text())
            for dds in subtype_variables.find_all('dd'):
                definitions.append(dds.get_text())

            for i in range(0, len(terms)):
                def_list = [j.strip() for j in definitions[i].splitlines()]
                def_list = list(filter(None, def_list))
                subtype_properties.append({terms[i]: def_list})

            subtype_metadata = {
                'name': resource_type.get('name'),
                'description': text_cleanup(subtype_description),
                'properties': subtype_properties,
                'url': f'{base_url}/{resource_type.get("url")}'
            }

            logging.debug(json.dumps({
                "subtype_description": subtype_description,
                "subtype_yaml": subtype_yaml,
                "subtype_properties": subtype_properties,
                "subtype_metadata": subtype_metadata
            }, indent=4, sort_keys=True))

            subtype_yaml.update({
                "MetaData": subtype_metadata
            })
            logging.debug(json.dumps(subtype_yaml, indent=4, sort_keys=True))
            subtypes.append(subtype_yaml)

        final_output[resource_name] = subtypes
        yaml_output = yaml.dump(json.loads(json.dumps(final_output)), indent=2, allow_unicode=True)
        logging.debug(yaml_output)
        save_page(f'Resources/{resource_name}.template', yaml_output)


def save_page(name=None, content=None):
    if name and content:
        with open(name, 'w') as file:
            file.write(content)
    else:
        raise Exception('Invalid file name or content.')


def get_page(url=None):
    try:
        name = url.split('/')[-1]
        logging.info(json.dumps({
            "method": "get_page",
            "url": url
        }, indent=4, sort_keys=True))

        if os.path.exists(f'scratch/{name}'):
            logging.debug('Cache File Found.')
            with open(f'scratch/{name}', "r") as file:
                text = file.read()
            file.close()
        else:
            logging.debug('Fetching from online.')
            time.sleep(1)
            response = requests.get(url)
            text = response.text
        save_page(f'scratch/{name}', text)
        tree = BeautifulSoup(text, 'html.parser')
        return tree
    except HTTPError as http_error:
        print(f'Http error occurred: {http_error}')
    except Exception as err:
        print(f'Other Error occurred: {err}')


get_resource_pages()
get_resource_subtypes()
collect_subtypes_for_resource()
