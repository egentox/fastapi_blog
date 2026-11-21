from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models
from app.auth import CurrentUser
from app.database import get_db
from app.schemas import (
    PaginatedPostsResponse,
    PostCreate,
    PostLikesResponse,
    PostResponse,
    PostUpdate,
)

router = APIRouter()


@router.post(
    "",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_post(
    post: PostCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    new_post = models.Post(
        title=post.title,
        content=post.content,
        user_id=current_user.id,
    )
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])
    return new_post


@router.get("", response_model=PaginatedPostsResponse)
async def get_posts(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    count_result = await db.execute(select(func.count()).select_from(models.Post))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .order_by(models.Post.date_posted.desc())
        .offset(skip)
        .limit(limit)
    )
    posts = result.scalars().all()

    has_more = skip + len(posts) < total

    return PaginatedPostsResponse(
        posts=[PostResponse.model_validate(post) for post in posts],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = result.scalars().first()
    if post:
        return post
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@router.put("/{post_id}", response_model=PostResponse)
async def update_post_full(
    post_id: int,
    post_data: PostCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this post",
        )

    post.title = post_data.title
    post.content = post_data.content
    post.user_id = post_data.user_id

    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post


@router.get("/{post_id}/like", response_model=PostLikesResponse)
async def get_post_likes(
    current_user: CurrentUser,
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    post_result = await db.execute(
        select(models.Post).where(models.Post.id == post_id)
    )
    post = post_result.scalar_one_or_none()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
    like_result = await db.execute(
        select(models.PostLike).where(
            models.PostLike.post_id == post_id,
            models.PostLike.user_id == current_user.id,
        )
    )
    like = like_result.scalar_one_or_none()
    return {
        "post_id": post.id,
        "liked": like is not None,
        "likes_count": post.likes,
    }


@router.put("/{post_id}/like", response_model=PostLikesResponse)
async def like_post(
    current_user: CurrentUser,
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    post_result = await db.execute(
        select(models.Post).where(models.Post.id == post_id)
    )
    post = post_result.scalar_one_or_none()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
    results = await db.execute(
        select(models.PostLike).where(
            models.PostLike.post_id == post_id,
            models.PostLike.user_id == current_user.id,
        )
    )
    like = results.scalar_one_or_none()
    if like is None:
        db.add(models.PostLike(user_id=current_user.id, post_id=post_id))
        post.likes += 1
        await db.commit()
    return {
        "post_id": post_id,
        "liked": True,
        "likes_count": post.likes,
    }


@router.delete("/{post_id}/like", response_model=PostLikesResponse)
async def unlike_post(
    current_user: CurrentUser,
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    post_result = await db.execute(
        select(models.Post).where(models.Post.id == post_id)
    )
    post = post_result.scalar_one_or_none()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    like_result = await db.execute(
        select(models.PostLike).where(
            models.PostLike.post_id == post_id,
            models.PostLike.user_id == current_user.id,
        )
    )
    like = like_result.scalar_one_or_none()
    if like is not None:
        await db.delete(like)
        post.likes -= 1
        await db.commit()

    return {
        "post_id": post.id,
        "liked": False,
        "likes_count": post.likes,
    }


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post_partial(
    post_id: int,
    post_data: PostUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this post",
        )

    update_data = post_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(models.PostLike).where(models.PostLike.id == post_id)
    )
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this post",
        )

    await db.delete(post)
    await db.commit()
