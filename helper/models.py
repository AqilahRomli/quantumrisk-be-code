from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime


class Item(BaseModel):
    question: str
    username: str
    # stakeholder: str
class getDataItem(BaseModel):
    question: str
    question_id: str
    timestamp: datetime
class Item1(BaseModel):
    question: str

class Details(BaseModel):
    projectName: str
    vertical: str
    projectDesc: str
    product: List[str]  # Ensure it expects a list of strings

class User(BaseModel):
    username: str
    password: str

class RegisterUser(BaseModel):
    username_requestor: Optional[str] = None  # ignored, requestor is taken from the token
    fullname: str
    username: str
    email: str
    staffId: str
    division: str
    user_role: str
    user_access: str

# Register one or more users (individual form = a list of one, bulk = the uploaded rows).
# The frontend has the same limit (helpers/new-user.ts) and the template has 500 rows.
MAX_USERS_PER_REGISTER = 500

class RegisterUsers(BaseModel):
    users: List[RegisterUser] = Field(..., min_length=1, max_length=MAX_USERS_PER_REGISTER)

class UpdateRole(BaseModel):
    username_requestor: str
    username: str
    id: str
    role: str

class UpdateRoleDetail(BaseModel):
    role_id: int
    role_name: str
    permission_ids: List[int]

class CreateRoleDetail(BaseModel):
    role_name: str
    permission_ids: List[int]

class DeleteRoleDetail(BaseModel):
    role_id: int

class CreatePermission(BaseModel):
    name: str
    group: str
    description: str

class DeletePermission(BaseModel):
    permission_id: int

class UpdateUserAccess(BaseModel):
    user_id: int
    role_id: int
    permission_ids: List[int]

class UpdateUserStatus(BaseModel):
    user_id: int
    is_active: bool

class AdminChangePassword(BaseModel):
    username: str
    id: str
    newpassword: str

class BulkDeleteRequest(BaseModel):
    question_ids: List[str]

# Define RiskData Model
class RiskDetail(BaseModel):
    customer_name: str
    project_name: str
    gm_name: str
    agm_name: str
    manager_name: str
    assistant_manager_name: str
    vertical: str
    sfdc_id: str
    project_description: str
    product_service_offering: str
    custom_product_components: str
    risk_category: str
    risk_event: str
    root_cause: str
    risk_impact: str
    likelihood: str
    impact: str
    likelihood_justification: str
    impact_justification: str
    risk_rating: str
    key_mitigation: str
    residual_risk_rating: str
    control_owner: str
    
class RiskRegistrationRequest(BaseModel):
    customer: str
    projectName: str
    risk_detail: List[RiskDetail]

class RiskUpdateRequest(BaseModel):
    proposalId: str
    customer: str
    projectName: str
    risk_detail: List[RiskDetail]

class UserLog(BaseModel):
    username: str
    activity: str
    status: str

# Define HistoryData Model
class HistoryData(BaseModel):
    username: str
    ques_id: str
    question: str
    risk_id: str
    stakeholder: str
    timestamp: datetime
    keyword: str

# Define HistoryAddInfoData Model
class HistoryAddInfoData(BaseModel):
    username: str
    ques_id: str
    question: str
    risk_title: str
    risk_description: str
    risk_category: str
    risk_root_cause: str
    risk_impact: str
    risk_mitigation: str
    timestamp: datetime
    keyword: str 

# Define RiskData Model
class PMRiskData(BaseModel):
    stakeholder: str
    customer_name: str
    project_name: str
    project_vertical: str
    project_type: str
    risk_id: str
    risk_category: str
    specific_risk: str
    risk_event: str
    risk_root_cause: str
    risk_impact: str
    likelihood_level: str
    likelihood_justification: str
    impact_level: str
    impact_justification: str
    risk_rating: str
    risk_mitigation_plan: str
    risk_mitigation_control_owner_group: str

class SCRiskData(BaseModel):
    stakeholder:str
    risk_id:str
    customer: str
    project_name: str
    vertical: str
    project_description: str
    product_service_offering: str
    risk_category: str
    risk_desc: str
    risk_event: Optional[str] = None
    root_cause: Optional[str] = None
    risk_impact: Optional[str] = None
    likelihood: str
    likelihood_justification: str
    impact: str
    impact_justification: str
    risk_rating: str
    key_mitigation: str
    residual_risk_rating: str
    control_owner: str
# Download history (Ask Me page -> Downloaded page)
MAX_ROWS_PER_SOURCE = 500

class DownloadRecord(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_type: Literal["xlsx", "pptx"]
    pm_data: List[dict] = Field(default_factory=list, max_length=MAX_ROWS_PER_SOURCE)
    sc_data: List[dict] = Field(default_factory=list, max_length=MAX_ROWS_PER_SOURCE)
    ll_data: List[dict] = Field(default_factory=list, max_length=MAX_ROWS_PER_SOURCE)
    issue_data: List[dict] = Field(default_factory=list, max_length=MAX_ROWS_PER_SOURCE)
    add_info: List[dict] = Field(default_factory=list, max_length=MAX_ROWS_PER_SOURCE)

class BulkDeleteDownloadRequest(BaseModel):
    download_ids: List[str] = Field(..., min_length=1)
