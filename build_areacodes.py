import os
import logging

import time

import json
import openai

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv


MAIN_URL = "https://www.nationalnanpa.com/tools/index.html"
SEARCH_LINK_TEXT = "Area Code Search"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def navigate_to_search_page(driver: any):
    try:
        # Navigate to the main page
        driver.get(MAIN_URL)

        # Find the "Area Code Search" link and click on it
        search_link = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.LINK_TEXT, SEARCH_LINK_TEXT))
        )
        search_link.click()

        logging.info("Navigated to the search page")
    except Exception as err:
        logging.error("Error occurred while navigating to the search page")
        logging.error(err)
        raise

def search_area_code(driver: any, area_code: str) -> tuple[bool, str, str]:
    # bool to return
    code_used = False
    # location
    code_location = ""
    #country
    code_country = ""

    try:
        # Find the form elements
        npa_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "npaValue"))
        )
        submit_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit']"))
        )

        # Fill in the area code and submit the form
        npa_input.clear()
        npa_input.send_keys(area_code)
        submit_button.click()

       # Wait for the results page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Get the HTML content of the page body
        html_content = driver.find_element(By.TAG_NAME, "body").get_attribute("outerHTML")

        logging.info(f"Successfully body data for area code: {area_code}")
        logging.info(f"Sending body HTML to LLM for interpretation")

        # send to local llm to get table data
        try:
            logging.info("==================")
            logging.info("OPENAI API LLM")
            logging.info("==================")

            oai_client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            prompt_content = f"""
Using the HTML website content provided, produce a JSON ONLY about the area code {area_code}. If there is no infomation, return an empty JSON.

If you cannot figure out how to extract the data create a JSON with a reason attribute and the value with the reason

RETURN ONLY JSON. RETURN JSON THAT WILL NOT CAUSE AN ERROR WITH PYTHON JSON MODULE. NO MARKDOWN

FOLLOW THIS EXAMPLE'S FORMAT
"""
            prompt_content += """
{ 
    "area_code": 200,
    "general_information": {
        "type_of_code": "Easily Recognizable Code",
        "assignable": "Yes",
        "geographic_or_non_geographic": "Non-geographic (N)",
        "code_reserved_for_future_use": "No",
        "code_assigned": "No",
        "code_in_use": "No"
    },
    "geographic_information": {
        "location": "",
        "country": "",
        "time_zone": "",
        "parent_npa": "",
        "overlay_code": "",
        "overlay_complex": "",
        "jeopardy": "",
        "relief_planning_in_progress": "No"
    }
}
"""
            prompt_content += f"HTML Content:\n{html_content}"

            llm_comp = oai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional Data Scientist named AreaCoder"
                    },
                    {
                        "role": "user",
                        "content": prompt_content
                    }
                ]
            )

            try:
                zip_json_data = json.loads(llm_comp.choices[0].message.content)
            except json.JSONDecodeError as err:
                logging.error(f"json error: {err}")
                zip_json_data = {}

            if zip_json_data:
                gen_info = zip_json_data["general_information"]
                geo_info = zip_json_data["geographic_information"]


                ciu = gen_info["code_in_use"]
                code_used = False if ciu == "N" or ciu == "No" else True
                code_location = geo_info["location"] if geo_info["location"] else ""
                code_country = geo_info["country"] if geo_info["country"] else ""

        except Exception as err:
            logging.error(f"OPENAI API error: {err}")

    except Exception as err:
        logging.error(f"Error occurred while retrieving data for area code: {area_code}")
        logging.error(err)
        raise

    return (code_used, code_location, code_country)

def main():

    driver = webdriver.Chrome()  # Make sure you have the appropriate WebDriver installed

    used_areacodes = [
        ["area_code", "location", "country"]
    ]

    for i in range(2, 10):
        for j in range(10):
            for k in range(10):
                area_code = f"{i}{j}{k}"
                logging.info(f"Generating area code: {area_code}")
                try:
                    navigate_to_search_page(driver)
                    ac_valid, ac_loc, ac_country = search_area_code(driver, area_code)
                    if ac_valid:
                        ac_info = [area_code, ac_loc, ac_country]
                        logging.info(f"Adding ac_info: {ac_info}")
                        used_areacodes.append(ac_info)
                except Exception as err:
                    logging.error(err)
                    logging.info("Sleeping 60 seconds...")
                    time.sleep(60)

                logging.info("Sleeping 10 seconds...")
                time.sleep(10)

    logging.info(f"{len(used_areacodes)-1} valid area codes found")

    # export to CSV

    driver.quit()

if __name__ == "__main__":
    load_dotenv()
    main()