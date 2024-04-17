"""
Builds area code database from scraping NANPA
Stores data into an sqlite database
"""

import os
import logging
import time
import sqlite3

import json
import openai

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def navigate_to_search_page(driver: any):
    try:
        # Navigate to the main page
        driver.get("https://www.nationalnanpa.com/tools/index.html")

        # Find the "Area Code Search" link and click on it
        search_link = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.LINK_TEXT, "Area Code Search"))
        )
        search_link.click()

        logging.info("Navigated to the search page")
    except Exception as err:
        logging.error("Error occurred while navigating to the search page")
        logging.error(err)
        raise

def search_area_code(driver: any, area_code: str) -> tuple[bool, str, str, bool]:
    # bool to return
    code_used = False
    # location
    code_location = ""
    # country
    code_country = ""
    # assignable
    code_assignable = False

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
        logging.info(f"Sending body HTML to LLM for interpretation\n")

        # send to local llm to get table data
        try:
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

            llm_resp = llm_comp.choices[0].message.content
            logging.info(f"llm_resp\n{llm_resp}")
            try:
                zip_json_data = json.loads(llm_comp.choices[0].message.content)
            except json.JSONDecodeError as err:
                logging.error(f"json error: {err}")
                logging.info(f"Retrying with {area_code}")
                return search_area_code(driver, area_code)

            if zip_json_data:
                gen_info = zip_json_data["general_information"]
                geo_info = zip_json_data["geographic_information"]

                code_assignable = True if gen_info["assignable"] == "Yes" else False
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

    return (code_used, code_location, code_country, code_assignable)

def db_check():
    """
    Check if db is created with table area_codes
    """
    try:
        sqlcon = sqlite3.connect("valid_area_codes.sql")
        sqlcur = sqlcon.cursor()

        # check if area_code table exists
        ac_table_exists = sqlcur.execute("SELECT name FROM sqlite_master WHERE name='area_code'").fetchall()
        if ac_table_exists:
            logging.info("Skip creating table 'area_code'")
        else:
            logging.info("Creating table 'area_code' in valid_area_codes.sql database")
            sqlcur.execute("CREATE TABLE area_code (code varchar(3), location text, country text, assignable integer, valid integer)")
    except Exception as err:
        logging.error(f"db_check: {err}")
        raise

def already_checked(area_code: str) -> bool:
    """
    Checks if area code was already added to database
    """
    ac_checked = False

    try:
        sqlcon = sqlite3.connect("valid_area_codes.sql")
        sqlcur = sqlcon.cursor()

        res = sqlcur.execute(f"SELECT code FROM area_code WHERE code='{area_code}'")
        if res.fetchone() is not None:
            ac_checked = True
    except Exception as err:
        logging.error(f"already_checked failed: {err}")
    
    return ac_checked

def add_to_db(ac_info: tuple):
    try:
        sqlcon = sqlite3.connect("valid_area_codes.sql")
        sqlcur = sqlcon.cursor()

        sqlcur.execute(f"""
    INSERT INTO area_code VALUES (
        '{ac_info[0]}',
        '{ac_info[1]}',
        '{ac_info[2]}',
        {1 if ac_info[3] else 0},
        {1 if ac_info[4] else 0}
    )
        """)

        sqlcon.commit()
        logging.info(f"Area code {ac_info[0]} added to database\n")
    except Exception as err:
        logging.error(f"add_to_db error: {err}")
        raise

def update_to_db(ac_info: tuple):
    try:
        sqlcon = sqlite3.connect("valid_area_codes.sql")
        sqlcur = sqlcon.cursor()

        sqlcur.execute(f"""
        UPDATE area_codes SET
            location='{ac_info[1]}',
            country='{ac_info[2]}',
            assignable={1 if ac_info[3] else 0},
            valid={1 if ac_info[4] else 0}
        WHERE code='{ac_info[0]}'
            """)

        sqlcon.commit()
        logging.info(f"Area code {ac_info[0]} updated on database\n")
    except Exception as err:
        logging.error(f"update_to_db error: {err}")
        raise

def main():
    try:
        db_check()
    
        driver = webdriver.Chrome()  # Make sure you have the appropriate WebDriver installed

        logging.info("Preparing...")
        time.sleep(3)

        for i in range(6, 10):
            for j in range(10):
                for k in range(10):
                    area_code = f"{i}{j}{k}"
                    logging.info(f"Generating area code: {area_code}")
                    try:
                        navigate_to_search_page(driver)
                        ac_valid, ac_loc, ac_country, ac_assignable = search_area_code(driver, area_code)
                        ac_info = [area_code, ac_loc, ac_country, ac_assignable, ac_valid]
                        
                        # really long log of info
                        logging.info(f"Area Code Info")
                        logging.info(f"area_code: {area_code}")
                        logging.info(f"ac_loc: {ac_loc}")
                        logging.info(f"ac_country: {ac_country}")
                        logging.info(f"ac_assignable: {ac_assignable}")
                        logging.info(f"ac_valid: {ac_valid}")

                        if not already_checked(area_code):
                            add_to_db(ac_info)
                        else:
                            update_to_db(ac_info)
                    except Exception as err:
                        logging.error(err)
                        logging.info("Sleeping 60 seconds...")
                        time.sleep(60)

                    logging.info("Sleeping 10 seconds...")
                    time.sleep(10)

        driver.quit()
    except Exception as err:
        logging.error(f"main failed: {err}")
        exit()

if __name__ == "__main__":
    load_dotenv()
    main()