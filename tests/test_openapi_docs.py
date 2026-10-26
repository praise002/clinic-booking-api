"""Every endpoint documents its summary, description and each response it can return."""

from httpx import AsyncClient


async def test_every_operation_documents_its_responses(client: AsyncClient):
    spec = (await client.get("/openapi.json")).json()

    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            where = f"{method.upper()} {path}"
            assert operation.get("summary"), f"{where} has no summary"
            assert operation.get("description"), f"{where} has no description"
            for code, response in operation["responses"].items():
                assert response["description"] != "Successful Response", (
                    f"{where} {code} uses FastAPI's default description"
                )
                assert response["description"] != "Validation Error", (
                    f"{where} documents FastAPI's 422; bad input is a 400 here"
                )
                if code.startswith(("4", "5")):
                    schema = response["content"]["application/json"]["schema"]
                    assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, (
                        f"{where} {code} isn't documented as {{error}}"
                    )
