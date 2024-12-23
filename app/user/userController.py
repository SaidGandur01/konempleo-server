from sqlite3 import IntegrityError
import traceback
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func
from app.auth.authDTO import UserToken
from app.auth.authService import get_password_hash, get_user_current
from app.user.userService import userServices
from app.user.userDTO import User, UserAdminCreateDTO, UserCreateDTO, UserCreateWithCompaniesResponseDTO, UserInsert, UserUpdateDTO
from sqlalchemy.orm import Session
from app import deps
from typing import List, Optional

from models.models import Company, CompanyUser, UserEnum, Users


userRouter = APIRouter()
userRouter.tags = ['User']

@userRouter.post("/user/admin/", status_code=201, response_model=UserCreateWithCompaniesResponseDTO)
def create_user(
    *,
    user_in: UserAdminCreateDTO, 
    company_ids: Optional[List[int]] = None,  # Optional list of company IDs
    db: Session = Depends(deps.get_db), 
    userToken: UserToken = Depends(get_user_current)
) -> dict:
    """
    Create a new admin user in the database and optionally assign to companies.
    """  
    # Authorization check
    if userToken.role != UserEnum.super_admin:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")
    
    # Role validation
    if user_in.role not in [UserEnum.super_admin, UserEnum.admin]:
        raise HTTPException(status_code=400, detail="The user role must be either super_admin or admin.")
    
    try:
        # Step 1: Create the user
        user = userServices.create(
            db=db, 
            obj_in=UserInsert(**{
                'fullname': user_in.fullname,
                'email': user_in.email,
                'password': get_password_hash('deeptalent'),
                'role': user_in.role,
            })
        )

        associated_company_names = []  # To store associated company names

        # Step 2: Validate company IDs and create CompanyUser records
        if company_ids:
            # Fetch existing companies from the DB
            existing_companies = db.query(Company).filter(Company.id.in_(company_ids)).all()
            existing_company_ids = {company.id for company in existing_companies}

            # Check for invalid company IDs
            invalid_ids = set(company_ids) - existing_company_ids
            if invalid_ids:
                raise HTTPException(status_code=404, detail=f"Companies with IDs {list(invalid_ids)} not found.")

            # Create and save CompanyUser records explicitly
            for company in existing_companies:
                company_user = CompanyUser(
                    companyId=company.id,
                    userId=user.id
                )
                db.add(company_user)
                associated_company_names.append(company.name)

        db.commit()  # Commit the transaction after successful processing
        db.refresh(user)  # Refresh user instance to ensure it's up to date

        # Return user details along with associated company names
        return UserCreateWithCompaniesResponseDTO(
            id=user.id,
            fullname=user.fullname,
            email=user.email,
            role=user.role,
            associated_companies=associated_company_names
        )

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="User with this email already exists.")
    
    except Exception as e:
        db.rollback()
        print(f"Error occurred in create_user function: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An error occurred while creating the user.")

    
@userRouter.post("/user/", status_code=201, response_model=None)
def create_user(
    *,
    user_in: UserCreateDTO,
    company_id: Optional[int] = None,  # Single optional company ID
    db: Session = Depends(deps.get_db),
    userToken: UserToken = Depends(get_user_current)
) -> dict:
    """
    Create a new user in the database and optionally assign to a company.
    """  
    # Authorization check: Only 'company' role can create users
    if userToken.role != UserEnum.company:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")

    try:
        # Step 1: Create the user
        user = userServices.create(
            db=db, 
            obj_in=UserInsert(**{
                'fullname': user_in.fullname,
                'email': user_in.email,
                'password': get_password_hash('deeptalent'),
                'role': UserEnum.company_recruit,
            })
        )

        # Step 2: Validate the company ID and create CompanyUser record
        if company_id:
            # Check if the company exists
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail=f"Company with ID {company_id} not found.")

            # Create CompanyUser record
            company_user = CompanyUser(
                companyId=company.id,
                userId=user.id
            )
            db.add(company_user)

        db.commit()  # Commit transaction after all operations succeed

        return {"detail": "User created successfully."}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="User with this email already exists.")
    
    except Exception as e:
        db.rollback()
        print(f"Error occurred in create_user function: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An error occurred while creating the user.")

@userRouter.put("/user/admin/{user_id}", status_code=200, response_model=UserCreateWithCompaniesResponseDTO)
def update_user(
    *,
    user_id: int,
    user_in: UserAdminCreateDTO,
    company_ids: Optional[List[int]] = None,  # Optional list of company IDs
    db: Session = Depends(deps.get_db),
    userToken: UserToken = Depends(get_user_current)
) -> dict:
    """
    Update an existing admin user in the database and optionally update associated companies.
    """
    # Authorization check
    if userToken.role != UserEnum.super_admin:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")
    
    # Fetch the user
    user = db.query(Users).filter(Users.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Role validation
    if user_in.role not in [UserEnum.super_admin, UserEnum.admin]:
        raise HTTPException(status_code=400, detail="The user role must be either super_admin or admin.")
    
    try:
        # Step 1: Update user information
        user.fullname = user_in.fullname
        user.email = user_in.email
        user.phone = user_in.phone
        user.role = user_in.role
        db.add(user)

        associated_company_names = []  # To store associated company names

        # Step 2: Validate company IDs and update CompanyUser records
        if company_ids:
            # Fetch existing companies from the DB
            existing_companies = db.query(Company).filter(Company.id.in_(company_ids)).all()
            existing_company_ids = {company.id for company in existing_companies}

            # Check for invalid company IDs
            invalid_ids = set(company_ids) - existing_company_ids
            if invalid_ids:
                raise HTTPException(status_code=404, detail=f"Companies with IDs {list(invalid_ids)} not found.")

            # Get current CompanyUser records for the user
            current_company_users = db.query(CompanyUser).filter(CompanyUser.userId == user_id).all()
            current_company_ids = {cu.companyId for cu in current_company_users}

            # Identify records to remove and add
            to_remove = current_company_ids - existing_company_ids
            to_add = existing_company_ids - current_company_ids

            # Remove CompanyUser records
            if to_remove:
                db.query(CompanyUser).filter(
                    CompanyUser.userId == user_id,
                    CompanyUser.companyId.in_(to_remove)
                ).delete(synchronize_session=False)

            # Add new CompanyUser records
            for company_id in to_add:
                company_user = CompanyUser(
                    companyId=company_id,
                    userId=user_id
                )
                db.add(company_user)
                associated_company_names.append(
                    db.query(Company.name).filter(Company.id == company_id).scalar()
                )
        else:
            # If no company_ids provided, remove all associated CompanyUser records
            db.query(CompanyUser).filter(CompanyUser.userId == user_id).delete(synchronize_session=False)

        db.commit()  # Commit the transaction after successful processing
        db.refresh(user)  # Refresh user instance to ensure it's up to date

        # Return user details along with associated company names
        return UserCreateWithCompaniesResponseDTO(
            id=user.id,
            fullname=user.fullname,
            email=user.email,
            role=user.role,
            associated_companies=associated_company_names
        )

    except Exception as e:
        db.rollback()
        print(f"Error occurred in update_user function: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An error occurred while updating the user.")

    
@userRouter.get("/users/", status_code=200, response_model=List[User])
def get_users(
    *, db: Session = Depends(deps.get_db), userToken: UserToken = Depends(get_user_current)
) -> List[User]:
    """
    Gets users in the database along with the names of the companies they are related to,
    filtering out users and companies with is_deleted set to true.
    """
    if userToken.role not in [UserEnum.super_admin, UserEnum.admin]:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")
    
    try:
        # Query users along with related companies, filtering out is_deleted = true
        users_with_companies = db.query(
            Users,
            func.array_agg(Company.name).label("companies")
        ).outerjoin(
            CompanyUser, CompanyUser.userId == Users.id
        ).outerjoin(
            Company, Company.id == CompanyUser.companyId
        ).filter(
            Users.is_deleted == False,  # Exclude users with is_deleted = true
            Company.is_deleted == False  # Exclude companies with is_deleted = true
        ).group_by(
            Users.id
        ).all()
        
        # Format the response
        result = []
        for user, companies in users_with_companies:
            result.append(
                User(
                    id=user.id,
                    fullname=user.fullname,
                    email=user.email,
                    role=user.role,
                    active=user.active,
                    is_deleted=user.is_deleted,
                    suspended=user.suspended,
                    phone=user.phone,
                    companies=[company for company in companies if company]  # Filter out nulls
                )
            )
        return result

    except Exception as e:
        print(f"Error occurred in get_users function: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching the users")


@userRouter.get("/users/company/{company_id}", status_code=200, response_model=List[User])
def get_users_by_company(
    company_id: int, 
    db: Session = Depends(deps.get_db), 
    userToken: UserToken = Depends(get_user_current)
) -> List[User]:
    """
    Get all users associated with a given company, excluding deleted users and companies.
    """
    # Check if the requesting user has the required permissions
    if userToken.role not in [UserEnum.super_admin, UserEnum.company]:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")

    try:
        # Query to get all users related to the given company, filtering for non-deleted records
        users = db.query(Users).join(CompanyUser).join(Company).filter(
            CompanyUser.companyId == company_id,
            Users.is_deleted == False,  # Exclude deleted users
            Company.is_deleted == False  # Exclude deleted companies
        ).all()

        if not users:
            raise HTTPException(status_code=404, detail=f"No users found for company ID: {company_id}")

        return users

    except Exception as e:
        print(f"Error occurred while fetching users for company ID {company_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching users for the company")


@userRouter.get("/users/me", status_code=200, response_model=User)
def get_current_user(
    *, db: Session = Depends(deps.get_db), userToken: UserToken = Depends(get_user_current)
) -> User:
    """
    Gets the current user's information along with the IDs and names of the companies they are related to.
    """
    try:
        # Query user along with related companies
        user_with_companies = db.query(
            Users,
            func.array_agg(
                func.json_build_object("id", Company.id, "name", Company.name)
            ).label("companies")
        ).outerjoin(
            CompanyUser, CompanyUser.userId == Users.id
        ).outerjoin(
            Company, Company.id == CompanyUser.companyId
        ).filter(
            Users.id == userToken.id
        ).group_by(
            Users.id
        ).first()
        
        # If the user does not exist
        if not user_with_companies:
            raise HTTPException(status_code=404, detail="User not found")

        # Extract user and companies
        user, companies = user_with_companies
        
        # Format the response
        return User(
            id=user.id,
            fullname=user.fullname,
            email=user.email,
            role=user.role,
            active=user.active,
            is_deleted=user.is_deleted,
            suspended=user.suspended,
            phone=user.phone,
            companies=[company for company in companies if company]  # Filter out nulls
        )

    except Exception as e:
        print(f"Error occurred in get_current_user function: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching the user information")
