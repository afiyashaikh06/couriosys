// Main JavaScript File

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });

    // Form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;
            
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    field.style.borderColor = '#e74c3c';
                    isValid = false;
                } else {
                    field.style.borderColor = '#ddd';
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                alert('Please fill in all required fields.');
            }
        });
    });

    // Mobile menu toggle (if needed)
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    const navLinks = document.querySelector('.nav-links');
    
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', function() {
            navLinks.classList.toggle('show');
        });
    }

    // Track parcel form focus
    const trackInput = document.querySelector('.track-input');
    if (trackInput) {
        trackInput.focus();
    }

    // Calculate parcel cost in real-time
    const calculateCost = () => {
        const weight = parseFloat(document.getElementById('weight')?.value) || 0;
        const parcelType = document.getElementById('parcel_type')?.value;
        const deliveryType = document.getElementById('delivery_type')?.value;
        const costSpan = document.getElementById('estimated-cost');
        
        if (weight && parcelType && deliveryType && costSpan) {
            let cost = 50;
            cost += weight * 10;
            
            const typeMultiplier = {
                'document': 1.0,
                'box': 1.2,
                'fragile': 1.5,
                'electronics': 1.3
            };
            
            const deliveryMultiplier = {
                'standard': 1.0,
                'express': 1.5
            };
            
            cost *= typeMultiplier[parcelType] || 1.0;
            cost *= deliveryMultiplier[deliveryType] || 1.0;
            
            costSpan.textContent = '₹ ' + cost.toFixed(2);
        }
    };

    // Attach event listeners for cost calculation
    const weightInput = document.getElementById('weight');
    const parcelTypeSelect = document.getElementById('parcel_type');
    const deliveryTypeSelect = document.getElementById('delivery_type');
    
    if (weightInput) weightInput.addEventListener('input', calculateCost);
    if (parcelTypeSelect) parcelTypeSelect.addEventListener('change', calculateCost);
    if (deliveryTypeSelect) deliveryTypeSelect.addEventListener('change', calculateCost);

    // Set minimum date for pickup date
    const pickupDate = document.getElementById('pickup_date');
    if (pickupDate) {
        const today = new Date().toISOString().split('T')[0];
        pickupDate.min = today;
    }

    // Confirm before cancelling parcel
    const cancelButtons = document.querySelectorAll('.cancel-btn');
    cancelButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to cancel this parcel?')) {
                e.preventDefault();
            }
        });
    });

    // Mark notification as read
    const notificationCards = document.querySelectorAll('.notification-card');
    notificationCards.forEach(card => {
        card.addEventListener('click', function() {
            if (!this.classList.contains('read')) {
                this.classList.add('read');
            }
        });
    });
});

// API call for tracking
async function trackParcel(trackingId) {
    try {
        const response = await fetch(`/api/track/${trackingId}`);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error tracking parcel:', error);
        return null;
    }
}

// Format date
function formatDate(dateString) {
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return new Date(dateString).toLocaleDateString('en-US', options);
}

// Toggle password visibility
function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
    input.setAttribute('type', type);
}

// function toggleDropdown() {
//     const dropdown = document.getElementById('userDropdown');
//     const arrow = document.querySelector('.dropdown-arrow');
//     dropdown.classList.toggle('show');
//     arrow.style.transform = dropdown.classList.contains('show') ? 'rotate(180deg)' : 'rotate(0)';
// }

// // Close dropdown when clicking outside
// document.addEventListener('click', function(event) {
//     const dropdown = document.getElementById('userDropdown');
//     const userInfo = document.querySelector('.user-info');
    
//     if (!userInfo.contains(event.target) && !dropdown.contains(event.target)) {
//         dropdown.classList.remove('show');
//         document.querySelector('.dropdown-arrow').style.transform = 'rotate(0)';
//     }
// });

// // Close dropdown when pressing Escape key
// document.addEventListener('keydown', function(event) {
//     if (event.key === 'Escape') {
//         const dropdown = document.getElementById('userDropdown');
//         dropdown.classList.remove('show');
//         document.querySelector('.dropdown-arrow').style.transform = 'rotate(0)';
//     }
// });
