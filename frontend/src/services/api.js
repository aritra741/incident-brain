import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

export const incidentService = {
  create: async (data) => (await api.post('/incidents/', data)).data,
  list: async (status = null) => (await api.get('/incidents/', { params: status ? { status } : {} })).data,
  get: async (id) => (await api.get(`/incidents/${id}`)).data,
  update: async (id, data) => (await api.patch(`/incidents/${id}`, data)).data,
  resolve: async (id) => (await api.post(`/incidents/${id}/resolve`)).data,
  delete: async (id) => (await api.delete(`/incidents/${id}`)).data,
};

export const eventService = {
  createText: async (incidentId, content, source = 'slack', actor = null) => {
    const params = new URLSearchParams({ incident_id: incidentId, content, source });
    if (actor) params.append('actor', actor);
    return (await api.post(`/events/text?${params.toString()}`)).data;
  },
  createImage: async (incidentId, imageFile, source = 'screen', actor = null) => {
    const formData = new FormData();
    formData.append('incident_id', incidentId);
    formData.append('image', imageFile);
    formData.append('source', source);
    if (actor) formData.append('actor', actor);
    return (await api.post('/events/image', formData, { headers: { 'Content-Type': 'multipart/form-data' } })).data;
  },
  getByIncident: async (incidentId, type = null) => {
    return (await api.get(`/events/incident/${incidentId}`, { params: type ? { event_type: type } : {} })).data;
  },
  getAnalysis: async (incidentId) => {
    return (await api.get(`/events/incident/${incidentId}/analysis`)).data;
  },
};

export const postmortemService = {
  generate: async (incidentId) => (await api.post(`/postmortems/generate/${incidentId}`)).data,
  get: async (incidentId) => (await api.get(`/postmortems/incident/${incidentId}`)).data,
  exportMarkdown: async (incidentId) => (await api.get(`/postmortems/incident/${incidentId}/markdown`, { responseType: 'text' })).data,
};

export const predictionService = {
  getByIncident: async (incidentId) => (await api.get(`/predictions/incident/${incidentId}`)).data,
  getAccuracy: async (incidentId) => (await api.get(`/predictions/incident/${incidentId}/accuracy`)).data,
  generate: async (incidentId) => (await api.post(`/predictions/generate/${incidentId}`)).data,
  updateOutcome: async (predictionId, outcome, actualTime = null) => {
    const params = new URLSearchParams({ outcome });
    if (actualTime !== null) params.append('actual_time_to_failure_minutes', actualTime);
    return (await api.post(`/predictions/${predictionId}/outcome?${params.toString()}`)).data;
  },
};

export const demoService = {
  seed: async () => (await api.post('/demo/seed')).data,
  seedWarnings: async () => (await api.post('/demo/seed-warnings')).data,
  replay: async () => (await api.post('/demo/replay')).data,
};

export default api;
