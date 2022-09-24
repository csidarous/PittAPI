"""
The Pitt API, to access workable data of the University of Pittsburgh
Copyright (C) 2015 Ritwik Gupta

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

import re
import requests
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

SUBJECTS_API = "https://prd.ps.pitt.edu/psc/pitcsprd/EMPLOYEE/SA/s/WEBLIB_HCX_CM.H_COURSE_CATALOG.FieldFormula.IScript_CatalogSubjects?institution=UPITT"
SUBJECT_COURSES_API = "https://prd.ps.pitt.edu/psc/pitcsprd/EMPLOYEE/SA/s/WEBLIB_HCX_CM.H_COURSE_CATALOG.FieldFormula.IScript_SubjectCourses?institution=UPITT&subject={subject}"
COURSE_DETAIL_API = "https://prd.ps.pitt.edu/psc/pitcsprd/EMPLOYEE/SA/s/WEBLIB_HCX_CM.H_COURSE_CATALOG.FieldFormula.IScript_CatalogCourseDetails?institution=UPITT&course_id={id}&effdt=2018-06-30&crse_offer_nbr=1&use_catalog_print=Y"
COURSE_SECTIONS_API = "https://prd.ps.pitt.edu/psc/pitcsprd/EMPLOYEE/SA/s/WEBLIB_HCX_CM.H_BROWSE_CLASSES.FieldFormula.IScript_BrowseSections?institution=UPITT&campus=&location=&course_id={id}&institution=UPITT&term={term}&crse_offer_nbr=1"
SECTION_DETAILS_API = "https://prd.ps.pitt.edu/psc/pitcsprd/EMPLOYEE/SA/s/WEBLIB_HCX_CM.H_CLASS_SEARCH.FieldFormula.IScript_ClassDetails?institution=UPITT&term={term}&class_nbr={id}"
    # id -> unique course ID, not to be confused with course code (for instance, CS 0007 has code 105611)
    # career -> for example, UGRD (undergraduate)

TERM_REGEX = "2\d\d[147]"
VALID_TERMS = re.compile(TERM_REGEX)

class Instructor(NamedTuple):
    name: str
    email: Optional[str] = None

class Meeting(NamedTuple):
    days: str
    start_time: str
    end_time: str
    start_date: str
    end_date: str
    instructors: Optional[List[Instructor]] = None

class Attribute(NamedTuple):
    attribute: str
    attribute_description: str
    attribute_value: str
    attribute_value_description: str

class Component(NamedTuple):
    component: str
    required: bool

class SectionDetails(NamedTuple):
    units: str

    class_capacity: str
    enrollment_total: str
    enrollment_available: str
    wait_list_capacity: str
    wait_list_total: str
    valid_to_enroll: str

    combined_section_numbers: Optional[List[str]] = None

class Section(NamedTuple):
    term: str
    session: str
    section_number: str
    class_number: str
    section_type: str
    status: str
    instructors: Optional[List[Instructor]] = None
    meetings: Optional[List[Meeting]] = None
    details: Optional[SectionDetails] = None

class Course(NamedTuple):
    subject_code: str
    course_number: str
    course_id: str
    course_title: str
    course_description: Optional[str] = None
    credit_range: Optional[Tuple[int]] = None
    requisites: Optional[str] = None
    components: List[Component] = None
    attributes: List[Attribute] = None
    sections: Optional[List[Section]] = None

class Subject(NamedTuple):
    subject_code: str
    courses: Dict[str, Course]

def get_subject_courses(subject: str) -> Subject:
    subject = _validate_subject(subject)

    json_response = _get_subject_courses(subject)
    return Subject(
        subject_code=subject,
        courses={
            course["catalog_nbr"] : 
            Course(
                subject_code=subject,
                course_number=course["catalog_nbr"],
                course_id=course["crse_id"],
                course_title=course["descr"]
            ) for course in json_response["courses"]
        }
    )

def get_course_details(term: Union[str, int], subject: str, course: Union[str, int]) -> Course:
    term = _validate_term(term)
    subject = _validate_subject(subject)
    course = _validate_course(course)

    internal_course_id = _get_course_id(subject, course)
    json_response = _get_course_info(internal_course_id)["course_details"]
    json_response_details = _get_course_sections(internal_course_id, term)
    return Course(
        subject_code=subject,
        course_number=course,
        course_id=internal_course_id,
        course_title=json_response_details["sections"][0]["descr"],
        course_description=json_response["descrlong"],
        credit_range=(json_response["units_minimum"], json_response["units_maximum"]),
        requisites=json_response["offerings"][0]["req_group"] if "offerings" in json_response and len(json_response["offerings"]) != 0 and "req_group" in json_response["offerings"][0] else None,
        components=[
            Component(
                component=component["descr"],
                required=True if component["optional"] == 'N' else False
            ) for component in json_response["components"]
        ] if "components" in json_response and len(json_response["components"]) != 0 else None,
        attributes=[
            Attribute(
                attribute=attribute["crse_attribute"],
                attribute_description=attribute["crse_attribute_descr"],
                attribute_value=attribute["crse_attribute_value"],
                attribute_value_description=attribute["crse_attribute_value_descr"]
            ) for attribute in json_response["attributes"]
        ] if "attributes" in json_response and len(json_response["attributes"]) != 0 else None,
        sections=[
            Section(
                term=term,
                session=section["session"],
                section_number=section["class_section"],
                class_number=str(section["class_nbr"]),
                section_type=section["section_type"],
                status=section["enrl_stat_descr"],
                instructors=[
                    Instructor(
                        name=instructor["name"],
                        email=instructor["email"]
                    ) for instructor in section["instructors"]
                ] if len(section["instructors"]) != 0 and section["instructors"][0] != "To be Announced" else None,
                meetings=[
                    Meeting(
                        days=meeting["days"],
                        start_time=meeting["start_time"],
                        end_time=meeting["end_time"],
                        start_date=meeting["start_dt"],
                        end_date=meeting["end_dt"],
                        instructors=[Instructor(name=meeting["instructor"])]
                    ) for meeting in section["meetings"]
                ] if len(section["meetings"]) != 0 else None
            ) for section in json_response_details["sections"]
        ]
    )

def get_section_details(term: Union[str, int], section_number: Union[str, int]) -> Section:
    term = _validate_term(term)
    
    json_response = _get_section_details(term, section_number)
    details = json_response["section_info"]["class_details"]
    meetings = json_response["section_info"]["meetings"]
    enrollment = json_response["section_info"]["class_availability"]

    return Section(
        term=term,
        session=details["session"],
        section_number=details["class_section"],
        class_number=str(section_number),
        section_type=details["component"],
        status=details["status"],
        instructors=None,
        meetings=[
            Meeting(
                days=meeting["stnd_mtg_pat"],
                start_time=meeting["meeting_time_start"],
                end_time=meeting["meeting_time_end"],
                start_date=meeting["start_date"],
                end_date=meeting["end_date"],
                instructors=[
                    Instructor(
                        name=instructor["name"],
                        email=instructor["email"]
                    ) for instructor in meeting["instructors"]
                ] if len(meeting["instructors"]) != 0 and meeting["instructors"][0]["name"] not in ["To be Announced", "-"] else None
            ) for meeting in meetings
        ] if len(meetings) != 0 else None,
        details=SectionDetails(
            units=details["units"],
            class_capacity=enrollment["class_capacity"],
            enrollment_total=enrollment["enrollment_total"],
            enrollment_available=str(enrollment["enrollment_available"]),
            wait_list_capacity=enrollment["wait_list_capacity"],
            wait_list_total=enrollment["wait_list_total"],
            valid_to_enroll=json_response["section_info"]["valid_to_enroll"],
            combined_section_numbers=[
                section["class_nbr"] for section in json_response["section_info"]["combined_sections"]
            ] if json_response["section_info"]["is_combined"] else None
        )
    )

# validation for method inputs
def _validate_term(term: Union[str, int]) -> str:
    """Validates that the term entered follows the pattern that Pitt does for term codes."""
    if VALID_TERMS.match(str(term)):
        return str(term)
    raise ValueError("Term entered isn't a valid Pitt term, must match regex " + TERM_REGEX)

def _validate_subject(subject: str) -> str:
    """Validates that the subject code entered is present in the API request."""
    if subject in _get_subject_codes():
        return subject
    raise ValueError("Subject code entered isn't a valid Pitt subject code.")

def _validate_course(course: Union[str, int]) -> str:
    """Validates that the course name entered is 4 characters long and in string form."""
    if course == "":
        raise ValueError("Invalid course number, please enter a non-empty string.")
    if (type(course) is str) and (not course.isdigit()):
        raise ValueError("Invalid course number, must be a number")
    if (type(course) is int) and (course <= 0):
        raise ValueError("Invalid course number, must be positive")
    course_length = len(str(course))
    if course_length < 4:
        return ("0" * (4 - course_length)) + str(course)
    elif course_length > 4:
        raise ValueError("Invalid course number, must be 4 characters long")
    return str(course)

# peoplesoft api calls
def _get_subjects() -> dict:
    return requests.get(SUBJECTS_API).json()

def _get_subject_courses(subject: str) -> dict:
    return requests.get(SUBJECT_COURSES_API.format(subject=subject)).json()

def _get_course_info(course_id: str) -> dict:
    response = requests.get(COURSE_DETAIL_API.format(id=course_id)).json()
    if response["course_details"] == {}:
        raise ValueError("Invalid course ID; course with that ID does not exist")
    return response

def _get_course_sections(course_id: str, term: str) -> dict:
    response = requests.get(COURSE_SECTIONS_API.format(id=course_id, term=term)).json()
    if len(response["sections"]) == 0:
        raise ValueError("Invalid course ID; course with that ID does not exist")
    return response

def _get_section_details(term: str, section_id: str) -> dict:
    response = requests.get(SECTION_DETAILS_API.format(term=term, id=section_id)).json()
    if "error" in response:
        raise ValueError("Invalid section ID; section with that ID does not exist")
    return response

# operations from api calls
def _get_subject_codes() -> List[str]:
    response = _get_subjects()
    codes = []
    for subject in response["subjects"]:
        codes.append(subject["subject"])
    return codes

def _get_internal_id_dict(subject: str) -> dict:
    response = _get_subject_courses(subject)
    internal_id_dict = {}
    for course in response["courses"]:
        if course["catalog_nbr"] not in internal_id_dict:
            internal_id_dict[course["catalog_nbr"]] = course["crse_id"]
    return internal_id_dict

def _get_course_id(subject: str, course: str) -> str:
    subject_dict = _get_internal_id_dict(subject)
    if str(course) not in subject_dict:
        raise ValueError("No course with that number within listed subject")
    return subject_dict[str(course)]