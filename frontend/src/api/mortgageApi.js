import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

function normaliseError(err) {
  if (err.code === 'ECONNABORTED')
    return 'Request timed out. The server is taking too long — please try again.';
  if (!err.response)
    return 'Cannot reach the server. Check your connection or try again shortly.';
  if (err.response.status === 429)
    return 'Too many requests. Please wait a moment before trying again.';
  if (err.response.status === 422)
    return 'Invalid input. Please check your values and try again.';
  return err.response?.data?.detail || 'Something went wrong. Please try again.';
}

export async function predictMortgage(formData) {
  try {
    const { data } = await client.post('/predict', formData);
    return { data, error: null };
  } catch (err) {
    return { data: null, error: normaliseError(err) };
  }
}

export async function calculateRenewal(formData) {
  try {
    const { data } = await client.post('/renew', formData);
    return { data, error: null };
  } catch (err) {
    return { data: null, error: normaliseError(err) };
  }
}

export async function getHistory(limit = 20) {
  try {
    const { data } = await client.get('/history', { params: { limit } });
    return { data, error: null };
  } catch (err) {
    return { data: null, error: normaliseError(err) };
  }
}
