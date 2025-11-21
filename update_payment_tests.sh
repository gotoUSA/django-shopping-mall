#!/bin/bash

# 비동기 결제 응답에 맞게 테스트 수정
# HTTP 200 → HTTP 202
# 응답 구조 변경

echo "Updating payment tests for async flow..."

# test_payment_confirm.py 수정
sed -i 's/assert response\.status_code == status\.HTTP_200_OK/assert response.status_code == status.HTTP_202_ACCEPTED/g' shopping/tests/payment/test_payment_confirm.py

# test_payment_validation.py 수정
sed -i 's/assert response\.status_code == status\.HTTP_200_OK/assert response.status_code == status.HTTP_202_ACCEPTED/g' shopping/tests/payment/test_payment_validation.py

# test_payment_points.py 수정
sed -i 's/assert response\.status_code == status\.HTTP_200_OK/assert response.status_code == status.HTTP_202_ACCEPTED/g' shopping/tests/payment/test_payment_points.py

# test_order_payment.py 수정
sed -i 's/assert response\.status_code == status\.HTTP_200_OK/assert response.status_code == status.HTTP_202_ACCEPTED/g' shopping/tests/order/test_order_payment.py

# test_payment_security.py 수정 (에러 케이스는 500 유지)
sed -i '/test_confirm_with_fake_payment_key_rejected/,/^$/! s/assert response\.status_code == status\.HTTP_200_OK/assert response.status_code == status.HTTP_202_ACCEPTED/g' shopping/tests/payment/test_payment_security.py

echo "✅ Status codes updated to 202 Accepted"
echo "Note: Response validation still needs manual updates"
