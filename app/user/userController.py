from sqlite3 import IntegrityError
import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from app.auth.authDTO import UserToken
from app.auth.authService import get_password_hash, get_user_current
from app.user.userService import generate_temp_password, send_email_with_temp_password, send_email_with_temp_resetpassword, userServices
from app.user.userDTO import CompanyUserDTO, ResetPasswordRequest, User, UserAdminCreateDTO, UserCreateDTO, UserCreateWithCompaniesResponseDTO, UserInsert, UserUpdateDTO, UserWCompanies, UserWithOfferCount
from sqlalchemy.orm import Session
from app import deps
from typing import List, Optional

from models.models import Company, CompanyUser, UserEnum, Users
from models.models import Offer as OfferModel


userRouter = APIRouter()
userRouter.tags = ['User']

@userRouter.post("/user/admin/", status_code=201, response_model=UserCreateWithCompaniesResponseDTO)
def create_user(
    *,
    user_in: UserAdminCreateDTO, 
    company_ids: Optional[List[int]] = None,  
    db: Session = Depends(deps.get_db), 
    userToken: UserToken = Depends(get_user_current)
) -> dict:
    """
    Create a new admin user in the database and optionally assign to companies.
    If sending the email fails, the user is NOT created.
    """  
    if userToken.role != UserEnum.super_admin:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")
    
    if user_in.role not in [UserEnum.super_admin, UserEnum.admin]:
        raise HTTPException(status_code=400, detail="The user role must be either super_admin or admin.")

    try:
        # Generate a random temp password
        temp_password = generate_temp_password()
        hashed_password = get_password_hash(temp_password)

        # Ensure phone is properly handled (if not provided, it should be None)
        phone_number = user_in.phone if user_in.phone else None

        # Step 1: Create the user (DO NOT COMMIT YET)
        user = userServices.create(
            db=db, 
            obj_in=UserInsert(**{
                'fullname': user_in.fullname,
                'email': user_in.email,
                'password': hashed_password,
                'role': user_in.role,
                'phone': phone_number,  # Ensure phone is explicitly saved
            })
        )

        associated_company_names = []

        # Step 2: Assign the user to companies (if provided)
        if company_ids:
            existing_companies = db.query(Company).filter(Company.id.in_(company_ids)).all()
            existing_company_ids = {company.id for company in existing_companies}
            invalid_ids = set(company_ids) - existing_company_ids
            if invalid_ids:
                db.rollback()  # Rollback in case of invalid company IDs
                raise HTTPException(status_code=404, detail=f"Companies with IDs {list(invalid_ids)} not found.")

            for company in existing_companies:
                company_user = CompanyUser(
                    companyId=company.id,
                    userId=user.id
                )
                db.add(company_user)
                associated_company_names.append(company.name)

        # Step 3: Try sending the email BEFORE committing
        try:
            send_email_with_temp_password(user.email, temp_password)
        except Exception as email_error:
            db.rollback()  # Rollback user creation if email sending fails
            raise HTTPException(status_code=500, detail=f"Failed to send email: {str(email_error)}")

        # Step 4: Now commit everything if email was sent successfully
        db.commit()
        db.refresh(user)

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
    
    except HTTPException as e:
        db.rollback()
        raise e  # Re-raise the HTTPException to keep the correct response
    
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
    Create a new user with the role of 'company_recruit' and optionally assign to a company.
    Sends a temporary password via email.
    If email sending fails, the user is NOT created.
    """  
    # Authorization check: Only 'company' role can create users
    if userToken.role != UserEnum.company:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")

    try:
        temp_password = generate_temp_password()
        hashed_password = get_password_hash(temp_password)

        # Ensure phone is properly handled (if not provided, store as None)
        phone_number = user_in.phone if hasattr(user_in, "phone") and user_in.phone else None

        # Step 1: Create the user (DO NOT COMMIT YET)
        user = userServices.create(
            db=db, 
            obj_in=UserInsert(**{
                'fullname': user_in.fullname,
                'email': user_in.email,
                'password': hashed_password,
                'role': UserEnum.company_recruit,
                'phone': phone_number,  # Ensure phone is explicitly saved
            })
        )

        # Step 2: Validate the company ID and create CompanyUser record
        if company_id:
            # Check if the company exists
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                db.rollback()  # Rollback if company does not exist
                raise HTTPException(status_code=404, detail=f"Company with ID {company_id} not found.")

            # Create CompanyUser record
            company_user = CompanyUser(
                companyId=company.id,
                userId=user.id
            )
            db.add(company_user)

        # Try sending the email BEFORE committing
        try:
            send_email_with_temp_password(user.email, temp_password)
        except Exception as email_error:
            db.rollback()  # Rollback user creation if email sending fails
            raise HTTPException(status_code=500, detail=f"Failed to send email: {str(email_error)}")

        # Now commit everything if email was sent successfully
        db.commit()
        db.refresh(user)

        return {"detail": "User created successfully."}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="User with this email already exists.")
    
    except HTTPException as e:
        db.rollback()
        raise e  # Re-raise the HTTPException to return the correct response
    
    except Exception as e:
        db.rollback()
        print(f"Error occurred in create_user function: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An error occurred while creating the user.")

@userRouter.put("/user/admin/{user_id}", status_code=200, response_model=UserWCompanies)
def update_user(
    *,
    user_id: int,
    user_in: UserUpdateDTO,
    company_ids: Optional[List[int]] = None,  # Optional list of company IDs
    db: Session = Depends(deps.get_db),
    userToken: UserToken = Depends(get_user_current)
) -> UserWCompanies:
    """
    Update an existing admin user in the database and optionally update associated companies.
    Prevent duplicate CompanyUser records for the same companyId and userId.
    """
    # Authorization check
    if userToken.role not in [UserEnum.super_admin, UserEnum.company]:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")

    # Fetch the user
    user = db.query(Users).filter(Users.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # Step 1: Update user information only if the field is provided
        if user_in.fullname is not None:
            user.fullname = user_in.fullname
        if user_in.email is not None:
            user.email = user_in.email
        if user_in.phone is not None:
            user.phone = user_in.phone
        if user_in.active is not None:
            user.active = user_in.active
        if user_in.is_deleted is not None:
            user.is_deleted = user_in.is_deleted
        db.add(user)

        # Step 2: Handle company_ids update only for super_admin users
        if userToken.role == UserEnum.super_admin:
            if company_ids:
                # Fetch existing companies from the DB
                existing_companies = db.query(Company).filter(Company.id.in_(company_ids), Company.is_deleted == False).all()
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
                    existing_record = db.query(CompanyUser).filter(
                        CompanyUser.companyId == company_id,
                        CompanyUser.userId == user_id
                    ).first()

                    if not existing_record:
                        company_user = CompanyUser(
                            companyId=company_id,
                            userId=user_id
                        )
                        db.add(company_user)
            else:
                # If no company_ids provided, remove all associated CompanyUser records
                db.query(CompanyUser).filter(CompanyUser.userId == user_id).delete(synchronize_session=False)

        db.commit()  # Commit the transaction after successful processing

        # Step 3: Refresh user and fetch associated companies
        db.refresh(user)
        associated_companies = db.query(
            Company.id, Company.name
        ).join(
            CompanyUser, Company.id == CompanyUser.companyId
        ).filter(
            CompanyUser.userId == user.id,
            Company.is_deleted == False
        ).all()

        # Return user details along with associated companies
        return UserWCompanies(
            id=user.id,
            fullname=user.fullname,
            email=user.email,
            role=user.role,
            active=user.active,
            is_deleted=user.is_deleted,
            phone=user.phone,
            companies=[
                CompanyUserDTO(id=company.id, name=company.name) for company in associated_companies
            ]
        )

    except Exception as e:
        db.rollback()
        print(f"Error occurred in update_user function: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An error occurred while updating the user")

    
@userRouter.get("/users/", status_code=200, response_model=List[UserWCompanies])
def get_users(
    *, db: Session = Depends(deps.get_db), userToken: UserToken = Depends(get_user_current)
) -> List[UserWCompanies]:
    """
    Gets users along with the IDs and names of the companies they are related to,
    filtering out users and companies with is_deleted set to true and ordering by created_at.
    """
    if userToken.role not in [UserEnum.super_admin, UserEnum.admin]:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")
    
    try:
        users_with_companies = db.query(
            Users,
            func.coalesce(
                func.array_agg(
                    func.json_build_object("id", Company.id, "name", Company.name)
                ).filter(Company.is_deleted == False),
                []
            ).label("companies")
        ).outerjoin(
            CompanyUser, CompanyUser.userId == Users.id
        ).outerjoin(
            Company, Company.id == CompanyUser.companyId
        ).filter(
            Users.is_deleted == False
        ).group_by(
            Users.id
        ).order_by(Users.created_at) \
        .all()
        
        result = []
        for user, companies in users_with_companies:
            formatted_companies = [
                CompanyUserDTO(**company) for company in companies if company and company.get("id") is not None
            ]
            result.append(
                UserWCompanies(
                    id=user.id,
                    fullname=user.fullname,
                    email=user.email,
                    role=user.role,
                    active=user.active,
                    is_deleted=user.is_deleted,
                    suspended=user.suspended,
                    phone=user.phone,
                    created_at=user.created_at,  # Pass created_at value
                    companies=formatted_companies
                )
            )
        return result

    except Exception as e:
        print(f"Error occurred in get_users function: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching the users")


@userRouter.get("/users/company/{company_id}", status_code=200, response_model=List[UserWithOfferCount])
def get_users_by_company(
    company_id: int, 
    db: Session = Depends(deps.get_db), 
    userToken: UserToken = Depends(get_user_current)
) -> List[UserWithOfferCount]:
    """
    Get all users associated with a given company, excluding deleted users and companies,
    along with the count of offers owned by each user, ordered by created_at.
    """
    if userToken.role not in [UserEnum.super_admin, UserEnum.company]:
        raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")

    try:
        users_with_offer_count = db.query(
            Users,
            func.count(OfferModel.id).filter(OfferModel.offer_owner == Users.id).label("offer_count")
        ).join(
            CompanyUser, CompanyUser.userId == Users.id
        ).join(
            Company, Company.id == CompanyUser.companyId
        ).outerjoin(
            OfferModel, OfferModel.offer_owner == Users.id
        ).filter(
            CompanyUser.companyId == company_id,
            Users.is_deleted == False,
            Company.is_deleted == False
        ).group_by(
            Users.id
        ).order_by(Users.created_at) \
        .all()

        if not users_with_offer_count:
            raise HTTPException(status_code=404, detail=f"No users found for company ID: {company_id}")

        result = [
            UserWithOfferCount(
                id=user.id,
                fullname=user.fullname,
                email=user.email,
                role=user.role,
                active=user.active,
                is_deleted=user.is_deleted,
                phone=user.phone,
                created_at=user.created_at,
                offer_count=offer_count
            )
            for user, offer_count in users_with_offer_count
        ]

        return result

    except Exception as e:
        print(f"Error occurred while fetching users for company ID {company_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching users for the company")


@userRouter.get("/users/me", status_code=200, response_model=UserWCompanies)
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
            func.coalesce(
            func.array_agg(
            func.json_build_object("id", Company.id, "name", Company.name)
            ).filter(Company.id.isnot(None)),  # Filter out null entries
            []
            ).label("companies")  # Default to an empty list
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
        return UserWCompanies(
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

@userRouter.get("/users/{userId}", status_code=200, response_model=UserWCompanies)
def get_user_by_id(
    *,
    userId: int,
    db: Session = Depends(deps.get_db),
    userToken: UserToken = Depends(get_user_current)
) -> UserWCompanies:
    """
    Gets a user's information along with the IDs and names of the companies they are related to by user ID.
    """
    try:
        # Check permissions: Only allow access if the user is a super_admin or admin
        if userToken.role not in [UserEnum.super_admin, UserEnum.admin, UserEnum.company]:
            raise HTTPException(status_code=403, detail="No tiene los permisos para ejecutar este servicio")

        # Query user along with related companies
        user_with_companies = db.query(
            Users,
            func.coalesce(
                func.array_agg(
                    func.json_build_object("id", Company.id, "name", Company.name)
                ).filter(Company.id.isnot(None)),  # Filter out null entries
                []
            ).label("companies")  # Default to an empty list
        ).outerjoin(
            CompanyUser, CompanyUser.userId == Users.id
        ).outerjoin(
            Company, Company.id == CompanyUser.companyId
        ).filter(
            Users.id == userId,  # Filter by the provided user ID
            Users.is_deleted == False  # Exclude deleted users
        ).group_by(
            Users.id
        ).first()

        # If the user does not exist
        if not user_with_companies:
            raise HTTPException(status_code=404, detail="User not found")

        # Extract user and companies
        user, companies = user_with_companies

        # Format the response
        return UserWCompanies(
            id=user.id,
            fullname=user.fullname,
            email=user.email,
            role=user.role,
            active=user.active,
            is_deleted=user.is_deleted,
            suspended=user.suspended,
            phone=user.phone,
            companies=[CompanyUserDTO(**company) for company in companies if company]  # Filter out nulls
        )

    except Exception as e:
        print(f"Error occurred in get_user_by_id function: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching the user information")

@userRouter.post("/user/reset-password", status_code=200, response_model=dict)
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(deps.get_db),
) -> dict:
    """
    Reset a user's password by generating a temporary password and marking 
    must_change_password as True. Sends the temporary password via email.
    """
    user = db.query(Users).filter(Users.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="No user found for the given email.")

    try:
        temp_password = generate_temp_password()
        hashed_password = get_password_hash(temp_password)

        user.password = hashed_password
        user.must_change_password = True
        db.add(user)
        db.commit()
        db.refresh(user)

        send_email_with_temp_resetpassword(user.email, temp_password)

        return {"detail": "Temporary password has been sent to the provided email."}

    except Exception as e:
        db.rollback()
        print(f"Error occurred in reset_password function: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while resetting the password.")